from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import repo_health as repo
import wpai_exec as app


class RepositoryTests(unittest.TestCase):
    def test_invalid_and_denied_requests_do_not_construct_reader(self):
        with patch.object(repo, "Reader") as reader:
            for arguments, status in (({"project": "another"}, "DENIED"),
                                      ({"project": "trackforge", "path": "C:/"}, "INVALID_ARGUMENTS"),
                                      ({"project": ["trackforge"]}, "INVALID_ARGUMENTS")):
                self.assertEqual(repo.health(arguments)["status"], status)
            reader.assert_not_called()

    def test_renamed_original_is_not_a_second_status_record(self):
        data = (b"2 R. fields destination\0? original\0"
                b"1 MM fields both\0u UU fields conflict\0? new\0")
        self.assertEqual(repo.count_status(data), {"staged": 3, "unstaged": 2, "untracked": 1, "conflicted": 1})

    def test_origin_mismatch_stops_git_after_identity(self):
        class OtherProjectReader(repo.Reader):
            def git(self, *args, **kwargs):
                raise repo.Unavailable("checkout_origin_mismatch")

            def github(self, *args, **kwargs):
                self.assert_identity(args)
                return {"id": 10, "full_name": repo.REPO, "private": True}

            def assert_identity(self, args):
                if args != ("",):
                    raise AssertionError("unexpected dependent network request")

        with patch.object(repo, "Reader", OtherProjectReader):
            result = repo.health({"project": "trackforge"})
        self.assertEqual(len(result["facts"]), 12)
        facts = result["facts"]
        self.assertEqual(facts["01_identity"]["value"]["remote"]["reason"], "remote_repository_identity_mismatch")
        self.assertEqual(facts["03_remote_main"]["reason"], "remote_identity_unavailable")
        self.assertEqual(facts["09_open_pull_requests"]["status"], "unavailable")
        self.assertEqual(facts["11_failed_checks"]["status"], "unavailable")

    def test_graph_counts_preserve_ahead_behind_direction(self):
        main, local = "a" * 40, "b" * 40

        class Graph:
            def git(self, *args):
                if args[-1] == "--is-shallow-repository":
                    return b"false\n"
                if args[-1] != f"{main}...{local}":
                    raise AssertionError("comparison direction")
                return b"2\t3\n"

        self.assertEqual(repo.divergence(Graph(), local, main),
                         {"ahead": 3, "behind": 2, "method": "local_object_graph"})

    def test_failed_jobs_preserve_step_and_unknown_cause(self):
        sample = {"id": 99, "name": "Tests", "conclusion": "failure"}
        timed_out = {"id": 100, "name": "Compile", "conclusion": "timed_out"}
        job = {"name": "Windows", "failed_steps": [{"number": 4, "name": "Test", "conclusion": "failure"}]}
        with patch.object(repo, "jobs", return_value={"items": [job], "truncated": False}):
            output = repo.failed_results(None, {
                "runs_main": repo.fact("runs", "main", {"items": [sample], "truncated": False}),
                "checks_main": repo.fact("checks", "main", {"items": [timed_out], "truncated": True}),
            })
        self.assertEqual(output["status"], "partial")
        failed, timeout = output["value"]["items"]
        self.assertEqual(failed["job_evidence"]["value"]["items"], [job])
        self.assertEqual(failed["cause"]["status"], "unavailable")
        self.assertEqual(timeout["cause"]["provider_conclusion"], "timed_out")

    def test_capped_process_output_and_deadline(self):
        reader = repo.Reader()
        with patch.object(repo, "MAX_CAPTURE", 1024):
            with self.assertRaisesRegex(repo.Unavailable, "capture_limit"):
                reader.run(sys.executable, ["-c", "print('a' * 4096)"], Path.cwd(), None, "test")
        with patch.object(repo, "COMMAND_SECONDS", 0.1):
            with self.assertRaisesRegex(repo.Unavailable, "test_timeout"):
                reader.run(sys.executable, ["-c", "import time; time.sleep(10)"], Path.cwd(), None, "test")

    def test_report_preserves_metadata_and_provenance_with_safe_display(self):
        sha = "a" * 40
        original_branch = "staging\u202e\u200b"
        raw_subject = "Café 修正 \x1b[31mtext\x1b[0m\u2028" + "x" * 120

        class OnlyLocal(repo.Reader):
            def github(self, *args, **kwargs):
                raise repo.Unavailable("offline_test")

            def git(self, *args, **kwargs):
                if args[0] == "log":
                    return f"{sha}\t2026-01-01T00:00:00Z\t{raw_subject}\n".encode()
                if args[0] == "symbolic-ref":
                    return (original_branch + "\n").encode()
                if args[0] == "rev-parse":
                    return (sha + "\n").encode()
                raise repo.Unavailable("not_in_fixture")

        with patch.object(repo, "Reader", OnlyLocal), patch.object(repo, "local_identity", return_value={}):
            payload = repo.health({"project": "trackforge"})
        facts = payload["facts"]
        self.assertEqual(payload["contract"], "wpai.repo_health.v1")
        self.assertEqual(len(facts), 12)
        self.assertEqual(facts["02_local_head"]["value"], {"branch": "staging", "sha": sha})
        history = facts["08_recent_commits"]["value"]["local_head"]
        self.assertEqual(history["source"], "git_log")
        self.assertEqual(history["value"][0]["subject"], ("Café 修正 text " + "x" * 120)[:112])
        self.assertEqual(repo.display_facts({"name": "build\x1b]0;title\x07\u2066", "failed_steps": [
            {"name": "run\tchecks\x9b0m", "conclusion": "failure"}]}), {
            "name": "build", "failed_steps": [{"name": "run checks", "conclusion": "failure"}]})

    def test_remote_commit_display_keeps_the_existing_subject_limit(self):
        reader = unittest.mock.Mock()
        reader.github.return_value = [{"sha": "b" * 40, "date": "2026-01-01T00:00:00Z",
                                       "subject": "\u2066Résumé\u2069 ✨ " + "z" * 130}]
        result = repo.remote_commits(reader, "b" * 40)
        self.assertEqual(result[0]["subject"], ("Résumé ✨ " + "z" * 130)[:112])


class TransportTests(unittest.TestCase):
    def test_size_limit_keeps_field_dispositions(self):
        facts = {f"{index:02}": repo.fact("git", "trackforge", "x" * (app.MAX_RESULT + 1))
                 for index in range(12)}
        with patch.object(app, "health", return_value={"contract": repo.CONTRACT, "status": "OK", "facts": facts}):
            payload, raw = app.result({"project": "trackforge"})
        self.assertLessEqual(len(raw), app.MAX_RESULT)
        self.assertEqual(len(payload["facts"]), 12)
        self.assertTrue(all(row["reason"] == "field_size_limit" for row in payload["facts"].values()))

if __name__ == "__main__":
    unittest.main()

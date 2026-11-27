import io
import json
from pathlib import Path
import sys
import threading
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


class TransportTests(unittest.TestCase):
    def test_size_limit_keeps_field_dispositions(self):
        facts = {f"{index:02}": repo.fact("git", "trackforge", "x" * (app.MAX_RESULT + 1))
                 for index in range(12)}
        with patch.object(app, "health", return_value={"contract": repo.CONTRACT, "status": "OK", "facts": facts}):
            payload, raw = app.result({"project": "trackforge"})
        self.assertLessEqual(len(raw), app.MAX_RESULT)
        self.assertEqual(len(payload["facts"]), 12)
        self.assertTrue(all(row["reason"] == "field_size_limit" for row in payload["facts"].values()))

    def test_cancelled_call_gets_no_reply(self):
        server = app.Stdio(io.BytesIO(), io.BytesIO())
        started = threading.Event()

        def collect(_arguments, cancellation):
            started.set()
            if not cancellation.wait(2):
                raise RuntimeError("cancellation was not delivered")
            return {"contract": repo.CONTRACT, "status": "OK"}

        with patch.object(app, "health", side_effect=collect):
            server.invoke(1, {"project": "trackforge"}, modern=True)
            self.assertTrue(started.wait(1))
            server.cancel(1)
            server.worker.join(3)
        self.assertFalse(server.worker.is_alive())
        self.assertEqual(server.outgoing.getvalue(), b"")

    def test_modern_discovery_bad_version_and_oversize_recovery(self):
        discover = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {
            app.META + "protocolVersion": app.MODERN, app.META + "clientCapabilities": {},
        }}}
        invalid = dict(discover, id=2)
        invalid["params"] = {"_meta": {app.META + "protocolVersion": "1900-01-01"}}
        incoming = b" " * (app.MAX_LINE * 2) + b"\n"
        incoming += b"\n".join(json.dumps(request).encode() for request in (discover, invalid)) + b"\n"
        outgoing = io.BytesIO()
        app.Stdio(io.BytesIO(incoming), outgoing).serve()
        limit, valid, wrong = [json.loads(row) for row in outgoing.getvalue().splitlines()]
        self.assertEqual(limit["error"]["code"], -32600)
        self.assertEqual(valid["result"]["supportedVersions"], list(app.SUPPORTED))
        self.assertEqual(wrong["error"]["code"], -32022)

    def test_legacy_initialization_and_denial_payload_parity(self):
        outgoing = io.BytesIO()
        server = app.Stdio(io.BytesIO(), outgoing)
        calls = [
            {"id": 1, "method": "tools/list"},
            {"id": 2, "method": "initialize", "params": {"protocolVersion": app.LEGACY[1], "capabilities": {}}},
            {"method": "notifications/initialized"},
            {"id": 3, "method": "tools/call", "params": {"name": app.TOOL, "arguments": {"project": "other"}}},
        ]
        with patch.object(repo, "Reader") as reader:
            for call in calls:
                server.handle_line(json.dumps({"jsonrpc": "2.0", **call}).encode())
            server.worker.join(2)
            reader.assert_not_called()
        early, hello, reply = [json.loads(row) for row in outgoing.getvalue().splitlines()]
        self.assertEqual(early["error"]["code"], -32002)
        self.assertEqual(hello["result"]["protocolVersion"], app.LEGACY[1])
        payload = reply["result"]
        self.assertEqual(json.loads(payload["content"][0]["text"]), payload["structuredContent"])
        self.assertTrue(payload["isError"])
        self.assertEqual(payload["structuredContent"]["status"], "DENIED")


if __name__ == "__main__":
    unittest.main()

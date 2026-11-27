from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from qualify_witness import qualify
from qualification import EXPECTED, run_case
from witness_record import GENESIS, canonical, digest, read_events, validate as legacy_validate
from verify_prior import ROOT, WORKFLOW, historical_workflow


def event_is(event, kind, **data):
    return event["kind"] == kind and all(event["data"].get(key) == value for key, value in data.items())


class ScenarioCompleteness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        records = TemporaryDirectory(prefix="wpai-witness-gate-")
        cls.addClassCleanup(records.cleanup)
        cls.paths = {scenario: Path(records.name) / f"{scenario}.jsonl" for scenario in EXPECTED}
        cls.process_results = {scenario: run_case(scenario, path) for scenario, path in cls.paths.items()}

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.edited = Path(directory.name) / "rechained.jsonl"

    def events(self, scenario):
        return read_events(self.paths[scenario])[0]

    def rechain(self, events, scenario):
        previous = GENESIS
        lines = []
        for seq, event in enumerate(deepcopy(events)):
            event.pop("sha256", None)
            event.update(run_id=events[0]["run_id"], seq=seq, previous=previous, monotonic_ns=seq)
            previous = digest(canonical(event))
            event["sha256"] = previous
            lines.append(canonical(event) + b"\n")
        self.edited.write_bytes(b"".join(lines))
        accepted, unfinished = read_events(self.edited)
        self.assertEqual(len(accepted), len(events))
        self.assertFalse(unfinished)
        return qualify(self.edited, scenario)

    def omit(self, scenario, label, kind, **data):
        before = self.events(scenario)
        after = [event for event in before if not event_is(event, kind, **data)]
        self.assertEqual(len(before) - len(after), 1)
        outcome = self.rechain(after, scenario)
        self.assertEqual(outcome["qualification"], "unavailable", outcome)
        self.assertIn(label, outcome["missing"])
        return outcome

    def test_external_owner_acknowledgment_is_required(self):
        outcome = self.omit("external_tree", "owner_acknowledged", "owner_acknowledged")
        self.assertEqual(outcome["lifecycle_status"], "observed_failure")
        self.assertEqual(legacy_validate(self.edited)["status"], "observed_failure")
        complete = qualify(self.paths["external_tree"], "external_tree")
        self.assertEqual(complete["qualification"], "pass")
        self.assertIn("server.stdin_eof", complete["unobserved"])
        self.assertIn("server.stdout_observation", complete["unobserved"])

    def test_external_receipt_check_is_required(self):
        outcome = self.omit("external_tree", "receipt_checked", "receipt_checked")
        self.assertEqual(outcome["lifecycle_status"], "observed_failure")

    def test_present_receipt_fails_external_scenario(self):
        records = self.events("external_tree")
        next(event for event in records if event_is(event, "receipt_checked"))["data"]["present"] = True
        outcome = self.rechain(records, "external_tree")
        self.assertEqual(outcome["lifecycle_status"], "observed_failure")
        self.assertEqual(outcome["qualification"], "fail")
        self.assertIn("receipt_checked", outcome["conflicts"])

    def test_external_wrapper_pipe_closure_is_required(self):
        self.omit("external_tree", "wrapper_stdout.terminal", "pipe_terminal", channel="wrapper_stdout")

    def test_wrapper_only_requires_server_alive_after_wrapper_exit(self):
        outcome = self.omit("wrapper_only", "server.active_after_wrapper_exit", "process_active", role="server")
        self.assertEqual(outcome["lifecycle_status"], "observed_failure")

    def test_wrapper_only_requires_one_active_member_checkpoint(self):
        self.omit("wrapper_only", "job.after_wrapper_exit", "job_accounting", checkpoint="after_wrapper_exit")
        records = self.events("wrapper_only")
        next(event for event in records if event_is(event, "job_accounting",
                                                    checkpoint="after_wrapper_exit"))["data"]["active"] = 0
        self.assertIn("job.after_wrapper_exit", self.rechain(records, "wrapper_only")["conflicts"])

    def test_descendant_liveness_and_post_root_job_counts_are_required(self):
        self.omit("descendant", "descendant.active_after_wrapper_exit", "process_active", role="descendant")
        records = self.events("descendant")
        next(event for event in records if event_is(event, "job_accounting",
                                                    checkpoint="after_wrapper_exit"))["data"]["active"] = 1
        self.assertIn("job.after_wrapper_exit", self.rechain(records, "descendant")["conflicts"])

    def test_local_close_requires_the_actual_server_stdout_terminal(self):
        self.omit("local_pipe_close", "server_stdout.local_close", "pipe_terminal", channel="server_stdout")
        records = self.events("local_pipe_close")
        terminal = next(event for event in records if event_is(event, "pipe_terminal", channel="server_stdout"))
        terminal["data"].update(outcome="peer_closed", source="ReadFile", winerror=109)
        result = self.rechain(records, "local_pipe_close")
        self.assertIn("server_stdout.local_close", result["conflicts"])

    def test_forced_pipe_closure_rejects_fabricated_graceful_markers(self):
        records = self.events("local_pipe_close")
        valid = self.events("normal")
        impostors = [event for event in valid if event["data"].get("role") == "server"
                     and event["kind"] in ("stdin_writer_closed", "fixture_marker")]
        records[-2:-2] = impostors
        result = self.rechain(records, "local_pipe_close")
        self.assertEqual(result["qualification"], "fail")
        self.assertIn("unexpected_graceful_markers", result["conflicts"])

    def test_well_chained_but_late_owner_acknowledgment_is_rejected(self):
        records = self.events("external_tree")
        ack = records.pop(next(i for i, event in enumerate(records) if event_is(event, "owner_acknowledged")))
        position = next(i for i, event in enumerate(records) if event_is(event, "force_requested", target="owner"))
        records.insert(position, ack)
        result = self.rechain(records, "external_tree")
        self.assertEqual(result["lifecycle_status"], "observed_failure")
        self.assertEqual(result["qualification"], "fail")
        self.assertIn("external_owner.wrapper.exit_order", result["conflicts"])

    def test_forced_eof_and_final_job_accounting_order_is_checked(self):
        records = self.events("external_tree")
        position = next(i for i, event in enumerate(records) if event_is(event, "force_requested", target="job"))
        pipe = records.pop(next(i for i, event in enumerate(records)
                                if event_is(event, "pipe_terminal", channel="wrapper_stdout")))
        records.insert(position, pipe)
        outcome = self.rechain(records, "external_tree")
        self.assertEqual(outcome["lifecycle_status"], "observed_failure")
        self.assertIn("wrapper.stdout_closure_after_force", outcome["conflicts"])
        records = self.events("descendant")
        checkpoint = records.pop(-2)
        records.insert(5, checkpoint)
        self.assertIn("descendant.exit_observation_order", self.rechain(records, "descendant")["conflicts"])

    def test_server_source_owner_boundary_and_unique_creation_ids(self):
        records = self.events("external_tree")
        next(event for event in records if event_is(event, "process_registered", role="server"))[
            "data"]["source"] = "created_handle"
        self.assertIn("server.registered", self.rechain(records, "external_tree")["conflicts"])
        records = self.events("external_tree")
        owner = next(event for event in records if event_is(event, "process_registered", role="owner"))
        owner["data"]["in_job"] = True
        self.assertEqual(self.rechain(records, "external_tree")["qualification"], "invalid")
        records = self.events("external_tree")
        records[2]["data"]["created"] = records[1]["data"]["created"]
        self.assertEqual(self.rechain(records, "external_tree")["qualification"], "invalid")

    def test_missing_control_or_timeout_evidence_cannot_pass(self):
        self.omit("channel_broken", "issue.channel_disconnected", "issue")
        self.omit("timeout", "issue.timeout", "issue")
        self.omit("normal", "server_control.terminal", "pipe_terminal", channel="server_control")

    def test_every_complete_case_passes_independently_of_lifecycle_status(self):
        for scenario, expected in EXPECTED.items():
            if scenario == "observer_crash":
                continue
            with self.subTest(scenario=scenario):
                verdict = qualify(self.paths[scenario], scenario)
                self.assertEqual(verdict["qualification"], "pass")
                self.assertEqual(verdict["lifecycle_status"], expected)
                self.assertEqual(verdict["missing"], [])
                self.assertEqual(verdict["conflicts"], [])

    def test_crash_and_truncated_record_never_qualify(self):
        result = qualify(self.paths["observer_crash"], "observer_crash")
        self.assertEqual(result["lifecycle_status"], "incomplete")
        self.assertEqual(result["qualification"], "incomplete")
        self.assertEqual(self.process_results["observer_crash"]["test_parent_after_observer_exit"],
                         {"observer_exit_code": 91, "active": 0})
        raw = self.paths["normal"].read_bytes()
        for truncated in (raw[:-1], b"".join(raw.splitlines(keepends=True)[:-1])):
            self.edited.write_bytes(truncated)
            self.assertEqual(qualify(self.edited, "normal")["qualification"], "incomplete")
        self.assertEqual(qualify(self.edited.with_suffix(".missing"), "normal")["qualification"], "unavailable")

    def test_tamper_duplicate_fields_and_trailing_data_still_fail(self):
        raw = self.paths["normal"].read_bytes()
        for edited in (raw.replace(b'"code":0', b'"code":7', 1),
                       raw.replace(b'"seq":0', b'"seq":0,"seq":0', 1), raw + b"{"):
            self.assertNotEqual(edited, raw)
            self.edited.write_bytes(edited)
            verdict = qualify(self.edited, "normal")
            self.assertEqual(verdict["qualification"], "invalid")
            self.assertEqual(verdict["conflicts"], ["v1_record"])

    def test_cli_is_deterministic_and_requires_the_declared_scenario(self):
        cli = [sys.executable, "-B", "-W", "error", str(HERE / "qualify_witness.py")]
        args = [*cli, "external_tree", str(self.paths["external_tree"])]
        a = subprocess.run(args, capture_output=True, timeout=10, check=True)
        b = subprocess.run(args, capture_output=True, timeout=10, check=True)
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(a.stderr, b"")
        mismatch = subprocess.run([*cli, "normal", str(self.paths["external_tree"])],
                                  capture_output=True, timeout=10)
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn(b'"scenario"', mismatch.stdout)

    def test_historical_ci_dispatch_cannot_hide_prior_workflow_edits(self):
        workflow = (ROOT / WORKFLOW).read_bytes()
        manifest = (ROOT / "outputs/stage-1.4/manifest.sha256").read_text(encoding="ascii")
        self.assertIn(b"stage-1.4/public_evidence.py", historical_workflow(workflow, manifest))
        with self.assertRaisesRegex(ValueError, "workflow prefix"):
            historical_workflow(workflow.replace(b"contents: read", b"contents: write", 1), manifest)


if __name__ == "__main__":
    unittest.main()

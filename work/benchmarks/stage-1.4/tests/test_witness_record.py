from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from observer import child_environment, observe
from windows import open_evidence
from witness_record import GENESIS, Ledger, MAX_LINE, canonical, digest, read_events, validate


class RecordIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "trusted.jsonl"
            observe("normal", path)
            cls.original = path.read_bytes()
            cls.events, unfinished = read_events(path)
            if unfinished or validate(path)["status"] != "observed_success":
                raise RuntimeError("Witness fixture did not produce a clean baseline")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "witness.jsonl"

    def rewritten(self, events):
        # Rechain to isolate semantic validation from hash verification.
        previous = GENESIS
        lines = []
        for seq, event in enumerate(events):
            event = {key: value for key, value in event.items() if key != "sha256"}
            event.update(seq=seq, previous=previous)
            previous = digest(canonical(event))
            event["sha256"] = previous
            lines.append(canonical(event) + b"\n")
        self.path.write_bytes(b"".join(lines))
        return validate(self.path)

    def test_missing_and_empty_records_fail_closed(self):
        self.assertEqual(validate(self.path)["status"], "unavailable")
        self.path.touch()
        self.assertEqual(validate(self.path)["status"], "incomplete")

    def test_tampering_and_duplicate_json_keys_are_rejected(self):
        self.path.write_bytes(self.original.replace(b'"code":0', b'"code":7', 1))
        self.assertEqual(validate(self.path)["status"], "invalid")
        self.path.write_bytes(self.original.replace(b'"seq":0', b'"seq":0,"seq":0', 1))
        self.assertEqual(validate(self.path)["status"], "invalid")

    def test_truncation_and_finalization_are_separate(self):
        lines = self.original.splitlines(keepends=True)
        for incomplete in (b"".join(lines[:-1]), self.original[:-2]):
            with self.subTest(size=len(incomplete)):
                self.path.write_bytes(incomplete)
                result = validate(self.path)
                self.assertEqual(result["status"], "incomplete")
                self.assertFalse(result["observer_finalized"])
        self.path.write_bytes(self.original + b"{")
        self.assertEqual(validate(self.path)["status"], "invalid")

    def test_exit_requires_an_independent_signal_event(self):
        missing_signal = [event for event in self.events
                          if not (event["kind"] == "handle_signaled" and event["data"]["role"] == "server")]
        self.assertEqual(self.rewritten(missing_signal)["status"], "invalid")

    def test_job_empty_alone_does_not_prove_exit_or_eof(self):
        sparse = [event for event in self.events if event["kind"] in (
            "observer_started", "job_accounting", "observer_finalized")]
        summary = self.rewritten(sparse)
        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(summary["job_accounting"]["final"]["active"], 0)
        self.assertEqual(summary["observed_exit_codes"], {})
        self.assertEqual(summary["stdin_eof_sources"], {})

    def test_mismatched_final_observer_identity_is_invalid(self):
        changed = deepcopy(self.events)
        changed[-1]["data"]["identity"] = "f" * 64
        self.assertEqual(self.rewritten(changed)["status"], "invalid")

    def test_monotonic_order_and_line_bounds(self):
        changed = deepcopy(self.events)
        changed[-1]["monotonic_ns"] = 0
        self.assertEqual(self.rewritten(changed)["status"], "invalid")
        self.path.write_bytes(b"x" * (MAX_LINE + 1))
        self.assertEqual(validate(self.path)["status"], "invalid")

    def test_enum_only_witness_payload_and_no_events_after_finalization(self):
        with open_evidence(self.path) as stream:
            ledger = Ledger(stream, "a" * 32)
            with self.assertRaises(ValueError):
                ledger.add("issue", **{"class": "unavailable", "code": "synthetic_unsafe_free_text"})
            ledger.add("observer_started", scenario="normal", identity="b" * 64, created="c" * 64, outside_job=True)
            ledger.add("observer_finalized", identity="b" * 64, outside_job=True, source="observer_terminal_record")
            with self.assertRaises(ValueError):
                ledger.add("issue", **{"class": "unavailable", "code": "missing_exit"})

    def test_observer_file_cannot_be_opened_for_overwrite_by_an_actor(self):
        # The actor is given the path here to prove the OS denies a second writer.
        code = ("import sys\ntry:\n open(sys.argv[1], 'wb').close()\n"
                "except PermissionError:\n sys.exit(27)\nsys.exit(6)\n")
        with open_evidence(self.path) as stream:
            stream.write(self.original)
            result = subprocess.run([sys.executable, "-I", "-S", "-B", "-W", "error", "-c", code, str(self.path)],
                                    stdin=subprocess.DEVNULL, capture_output=True, timeout=5, env=child_environment())
            self.assertEqual(result.returncode, 27)
            with self.assertRaises(OSError):
                open_evidence(self.path)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(validate(self.path)["status"], "observed_success")


if __name__ == "__main__":
    unittest.main()

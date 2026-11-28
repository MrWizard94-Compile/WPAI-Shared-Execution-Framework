"""Mutate and rechain real evidence so semantic validation is tested independently."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boundary import RECOVERY_MS
from contract import canonical, parse
from driver import run_case
from journal import validate
from witness import INITIAL, LINE_BYTES, LIMIT, seal


def at(records, event, **extra):
    return next(index for index, row in enumerate(records)
                if row["event"] == event and all(row.get(key) == value for key, value in extra.items()))


def rechain(records):
    previous = INITIAL
    result = []
    timestamp = 0
    for seq, original in enumerate(records, 1):
        row = {key: value for key, value in original.items() if key != "hash"}
        timestamp = max(timestamp, row["ns"])
        row.update(seq=seq, prev=previous, ns=timestamp)
        row = seal(row)
        previous = row["hash"]
        result.append(canonical(row) + b"\n")
    return b"".join(result)


class StrictJournal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normal = run_case("normal")[0]
        cls.failure = run_case("response_verified")[0]
        cls.early = run_case("normal", unexpected_loss=True)[0]

    def records(self, data=None):
        return [parse(line) for line in (data or self.failure).splitlines()]

    def reject(self, records):
        result = validate(rechain(records))
        self.assertFalse(result["valid"])
        self.assertEqual(result["outcome"], "invalid")

    def test_rechained_unmodified_control(self):
        self.assertTrue(validate(rechain(self.records()))["valid"])

    def test_forged_success_and_false_eof_fail(self):
        forged = self.records()
        forged[-1]["outcome"] = "observed_success"
        self.reject(forged)
        false_eof = self.records()
        entry = at(false_eof, "observation_unavailable", channel="fixture_request")
        false_eof[entry].update(event="terminal_read", status=109, bytes=0)
        self.reject(false_eof)

    def test_loss_requires_independent_terminal_pipe_and_retained_signal(self):
        for event in ("controller_pipe_terminal", "controller_lost", "signaled"):
            with self.subTest(event=event):
                records = self.records()
                del records[at(records, event)]
                self.reject(records)
        records = self.records()
        signal = records.pop(at(records, "signaled", role="controller"))
        records.insert(at(records, "exit", role="controller") + 1, signal)
        self.reject(records)

    def test_job_accounting_and_rights_cannot_be_relabelled(self):
        records = self.records()
        records[at(records, "job", scope="guard", phase="final")]["active"] = 1
        self.reject(records)
        records = self.records()
        records[at(records, "job", scope="fixture", phase="checkpoint")]["members"] = []
        self.reject(records)
        records = self.records()
        records[at(records, "witness_rights")]["jobs"]["guard"] |= 1
        self.reject(records)

    def test_recovery_bounds_and_causal_order_are_enforced(self):
        records = self.records()
        records[at(records, "recovery_settled")]["elapsed_ns"] = RECOVERY_MS * 1_000_000 + 1
        self.reject(records)
        records = self.records()
        records[at(records, "recovery_started")]["budget_ms"] = RECOVERY_MS * 2
        self.reject(records)
        records = self.records()
        force = records.pop(at(records, "recovery_force"))
        records.insert(at(records, "controller_lost"), force)
        self.reject(records)

    def test_duplicate_events_and_false_finalization_fail(self):
        records = self.records()
        records.insert(2, records[1])
        self.reject(records)
        records = self.records()
        self.reject(records + [records[-1]])
        records[-1]["process"] = "0" * 64
        self.reject(records)
        self.assertEqual(validate(rechain(self.records()[:-1]))["outcome"], "incomplete")

    def test_emergency_records_still_have_strict_prefix_and_terminal(self):
        records = self.records(self.early)
        records[at(records, "witness_ready")].update(forged=True)
        self.reject(records)
        records = self.records(self.early)
        records[at(records, "emergency")]["controller_terminal"] = None
        self.reject(records)

    def test_wire_checks_are_inherited_from_stage_16(self):
        records = self.records(self.normal)
        row = next(row for row in records if row.get("observation", {}).get("boundary") == "relay_response_write")
        row["observation"]["sha256"] = "0" * 64
        self.reject(records)

    def test_integrity_bounds_duplicate_keys_and_truncation(self):
        raw = self.normal
        for damaged in (b" " + raw, raw.replace(b'"event":"start"', b'"event":"start","event":"start"', 1),
                        raw.replace(b'"event":"start"', b'"event":"tampered"', 1),
                        b"a" * (LIMIT * LINE_BYTES + 1), b"a" * LINE_BYTES + b"\n"):
            self.assertEqual(validate(damaged)["outcome"], "invalid")
        self.assertEqual(validate(raw[:-1])["outcome"], "incomplete")

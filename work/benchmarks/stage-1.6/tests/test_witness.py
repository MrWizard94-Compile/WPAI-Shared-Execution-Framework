"""Verify the semantic gate with rechained edits of real Windows witness records."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract import SCENARIOS, canonical, parse
from observer import run_case
from win import open_evidence
from witness import INITIAL, LINE_BYTES, LIMIT, Ledger, SCHEMA, seal, validate


def select(records, event, **fields):
    return next(i for i, row in enumerate(records) if row.get("event") == event
                and all(row.get(key) == value for key, value in fields.items()))


def rechain(records):
    previous = INITIAL
    lines = []
    for sequence, event in enumerate(records, 1):
        row = dict(event)
        row.pop("hash")
        row.update(seq=sequence, prev=previous, ns=sequence * 1_000_000_000)
        row = seal(row)
        previous = row["hash"]
        lines.append(canonical(row) + b"\n")
    return b"".join(lines)


class StrictWitness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = {case: run_case(case)[0] for case in SCENARIOS}

    def records(self, scenario):
        return [parse(line) for line in self.raw[scenario].splitlines()]

    def reject_omission(self, scenario, event, **fields):
        records = self.records(scenario)
        del records[select(records, event, **fields)]
        self.assertEqual(validate(rechain(records))["lifecycle"], "invalid")

    def reject_update(self, recorded_case, event, selector, **changes):
        records = self.records(recorded_case)
        records[select(records, event, **selector)].update(changes)
        self.assertEqual(validate(rechain(records))["lifecycle"], "invalid")

    def test_registration_is_exact_and_distinct(self):
        self.reject_omission("normal", "registered", role="relay")
        records = self.records("normal")
        at = select(records, "registered", role="relay")
        records.insert(at, records[at])
        self.assertEqual(validate(rechain(records))["lifecycle"], "invalid")
        for identity in ("process", "creation"):
            records = self.records("normal")
            records[at][identity] = records[select(records, "registered", role="root")][identity]
            self.assertEqual(validate(rechain(records))["lifecycle"], "invalid")

    def test_membership_accounting_and_handle_signal_required(self):
        self.reject_update("normal", "registered", {"role": "relay"}, job="fixture")
        self.reject_update("normal", "job", {"job": "subject", "phase": "startup"}, active=1)
        self.reject_update("normal", "job", {"job": "fixture", "phase": "final"}, total=2)
        self.reject_omission("normal", "signaled", role="server")
        self.reject_update("normal", "exit", {"role": "server"}, code=True)

    def test_force_requires_live_subject_and_independent_survivors(self):
        self.reject_omission("external_termination", "active", role="owner", phase="after_subject_force")
        self.reject_omission("external_termination", "active", role="server", phase="after_subject_force")
        self.reject_omission("external_termination", "force_ack")
        records = self.records("external_termination")
        request = records.pop(select(records, "force_request"))
        records.insert(select(records, "exit", role="relay") + 1, request)
        self.assertEqual(validate(rechain(records))["lifecycle"], "invalid")

    def test_eof_needs_writer_close_and_both_transport_boundaries(self):
        self.reject_omission("normal", "server_empty_read")
        self.reject_omission("normal", "writer_close", channel="fixture_request")
        for channel in ("front_request", "front_response", "split_request", "split_response",
                        "fixture_request", "fixture_response"):
            with self.subTest(channel=channel):
                self.reject_omission("normal", "terminal_read", channel=channel)
        records = self.records("duplicate_writer")
        read = records.pop(select(records, "terminal_read", channel="fixture_request"))
        records.insert(select(records, "writer_close", writer="owner_duplicate"), read)
        self.assertEqual(validate(rechain(records))["lifecycle"], "invalid")
        self.reject_omission("duplicate_writer", "still_open")

    def test_relay_digest_and_byte_counts_are_independently_pinned(self):
        self.reject_update("normal", "wire", {"boundary": "relay_request_read"}, bytes=2)
        self.reject_update("normal", "wire", {"boundary": "relay_response_write"}, sha256="0" * 64)

    def test_owner_loss_cannot_be_converted_to_clean(self):
        self.reject_update("owner_loss", "start", {}, scenario="normal")
        self.reject_omission("owner_loss", "owner_lost")
        self.reject_update("owner_loss", "read_unavailable", {"channel": "fixture_request"}, bytes=0)

    def test_finalization_is_unique_and_terminal(self):
        records = self.records("normal")
        self.assertEqual(validate(rechain(records + [records[-1]]))["lifecycle"], "invalid")
        self.assertEqual(validate(rechain(records[:-1]))["lifecycle"], "incomplete")

    def test_integrity_rejects_duplicate_noncanonical_tampered_and_oversize_records(self):
        data = self.raw["normal"]
        self.assertEqual(validate(data[:-3])["lifecycle"], "incomplete")
        self.assertEqual(validate(data + b"{")["lifecycle"], "incomplete")
        for damaged in (b" " + data, data.replace(b'"event":"start",', b'"event":"start","event":"start",', 1),
                        data.replace(b'"event":"start"', b'"event":"final"', 1),
                        b"x" * (LINE_BYTES * LIMIT + 1), b"{" + b"x" * LINE_BYTES + b"}\n"):
            self.assertEqual(validate(damaged)["lifecycle"], "invalid")
        self.reject_update("normal", "start", {}, payload="unapproved field")

    def test_ledger_has_one_writer_and_flushes_each_complete_record(self):
        with TemporaryDirectory(prefix="wpai-split-ledger-") as fresh:
            path = Path(fresh) / "one-writer.jsonl"
            with open_evidence(path) as stream:
                ledger = Ledger(stream)
                ledger.add("start", schema=SCHEMA, scenario="normal")
                self.assertTrue(path.read_bytes().endswith(b"\n"))
                with self.assertRaises(PermissionError), path.open("ab"):
                    pass
            self.assertEqual(validate(path.read_bytes())["lifecycle"], "incomplete")

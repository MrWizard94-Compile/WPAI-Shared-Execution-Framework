"""Exercise kernel processes, job containment, pipe reads and recovery on Windows."""

import sys
from pathlib import Path
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract import RESPONSE_MARK, RESULTS, SCENARIOS
from observer import run_case


class WindowsSplitRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {case: run_case(case)[1] for case in SCENARIOS}

    def test_normal_verifies_fixture_and_both_directions(self):
        outcome = self.runs["normal"]
        self.assertEqual((outcome["lifecycle"], outcome["qualification"]), RESULTS["normal"])
        self.assertEqual(outcome["wire"]["response"], RESPONSE_MARK)
        self.assertEqual(len(outcome["ReadFile_terminal_status"]), 6)
        self.assertTrue(outcome["server_empty_read_attested"])
        self.assertEqual(outcome["exit_codes"], dict.fromkeys(("root", "relay", "owner", "server"), 0))

    def test_subject_force_preserves_fixture_boundary(self):
        outcome = self.runs["external_termination"]
        self.assertEqual((outcome["lifecycle"], outcome["qualification"]), RESULTS["external_termination"])
        self.assertEqual(outcome["exit_codes"], {"force": 0, "root": 124, "relay": 124, "owner": 0, "server": 0})
        self.assertEqual(outcome["force_isolation_probe"], "read_and_write_denied")
        self.assertTrue(outcome["server_empty_read_attested"])
        self.assertEqual(set(outcome["unavailable_reads"]), {"front_request", "front_response", "split_response"})
        self.assertEqual(outcome["job_accounting"]["fixture_after_subject_force"]["active"], 1)

    def test_duplicate_writer_holds_eof_until_released(self):
        outcome = self.runs["duplicate_writer"]
        self.assertEqual(outcome["duplicate_writer_window_ms"], 120)
        self.assertTrue(outcome["server_empty_read_attested"])
        self.assertEqual([close["writer"] for close in outcome["writer_closes"]
                          if close["channel"] == "fixture_request"], ["owner_primary", "owner_duplicate"])

    def test_owner_loss_remains_incomplete_after_recovery(self):
        outcome = self.runs["owner_loss"]
        self.assertEqual((outcome["lifecycle"], outcome["qualification"]), RESULTS["owner_loss"])
        self.assertEqual(outcome["exit_codes"]["owner"], 125)
        self.assertEqual(outcome["exit_codes"]["server"], 124)
        self.assertIn("owner_control", outcome["ReadFile_terminal_status"])
        self.assertNotIn("fixture_request", outcome["ReadFile_terminal_status"])
        self.assertFalse(outcome["server_empty_read_attested"])

    def test_all_scenarios_finalize_outside_empty_owned_jobs(self):
        for scenario, outcome in self.runs.items():
            with self.subTest(scenario=scenario):
                self.assertTrue(outcome["observer_finalized"])
                for target in ("subject", "fixture"):
                    self.assertEqual(outcome["job_accounting"][target + "_final"]["active"], 0)

    def test_stalled_startup_recovers_both_real_jobs(self):
        start = time.monotonic()
        _, outcome = run_case("normal", timeout_probe=True)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(outcome, {"lifecycle": "unavailable", "reason": "deadline", "bounded_recovery": True})

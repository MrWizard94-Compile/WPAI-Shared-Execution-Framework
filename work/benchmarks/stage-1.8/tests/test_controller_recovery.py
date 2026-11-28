"""Run fresh real Windows actors and exercise independent controller-loss recovery."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boundary import CASES, INJECTED_EXIT, JOBS, RECOVERY_MS, WITNESS_MASKS, fixed_actor_command
from contract import REQUEST, RESPONSE_MARK, observation
from driver import run_case
from journal import PIPE_ROLES
from witness import rows


class LiveControllerRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = {case: run_case(case) for case in CASES}

    def test_normal_stage16_transport_eof_and_real_exit_codes(self):
        _, result = self.cases["normal"]
        self.assertEqual(result["outcome"], "observed_success")
        self.assertEqual(result["wire"], {"request": observation(REQUEST), "response": RESPONSE_MARK})
        self.assertEqual(set(result["actor_terminal_ReadFile"]), set(PIPE_ROLES))
        self.assertEqual(result["fixture_eof"], "observed")
        self.assertEqual(result["exit_codes"], dict.fromkeys(("controller", "owner", "server", "root", "relay"), 0))
        self.assertIsNone(result["recovery_elapsed_ns"])

    def test_witness_was_distinct_ready_and_rights_limited(self):
        for case, (raw, _) in self.cases.items():
            with self.subTest(case=case):
                events = [row for row, _ in rows(raw)[0]]
                registrations = [row for row in events if row["event"] == "registered"]
                self.assertEqual([row["role"] for row in registrations[:2]], ["witness", "controller"])
                self.assertNotEqual(registrations[0]["process"], registrations[1]["process"])
                rights = next(row for row in events if row["event"] == "witness_rights")
                self.assertEqual(rights["jobs"], WITNESS_MASKS)
                self.assertTrue(all(mask & 1 == 0 for mask in rights["jobs"].values()))
                self.assertLess(next(i for i, row in enumerate(events) if row["event"] == "witness_ready"),
                                next(i for i, row in enumerate(events) if row["event"] == "protected_storage"))

    def test_all_abrupt_cases_detect_controller_exit_and_fail_closed(self):
        for case in CASES[1:]:
            with self.subTest(case=case):
                raw, result = self.cases[case]
                self.assertEqual(result["outcome"], "incomplete")
                self.assertTrue(result["valid"] and result["witness_finalized"] and result["controller_lost"])
                self.assertEqual(result["exit_codes"]["controller"], INJECTED_EXIT)
                self.assertEqual(result["fixture_eof"], "unavailable")
                self.assertEqual(set(result["unavailable"]), set(PIPE_ROLES))
                self.assertEqual(result["actor_terminal_ReadFile"], {})
                self.assertLessEqual(result["recovery_elapsed_ns"], RECOVERY_MS * 1_000_000)
                events = [row for row, _ in rows(raw)[0]]
                loss = next(i for i, row in enumerate(events) if row["event"] == "controller_lost")
                self.assertEqual(events[loss + 1]["phase"], "after_controller_loss")

    def test_fault_checkpoints_have_distinct_kernel_and_transport_proof(self):
        self.assertEqual(self.cases["before_launch"][1]["final_job_accounting"]["guard"]["total"], 1)
        self.assertEqual(self.cases["actors_verified"][1]["request_hops_before_loss"], 0)
        held = self.cases["in_flight"][1]
        self.assertEqual(held["request_hops_before_loss"], 3)
        self.assertEqual(held["wire"], {"request": observation(REQUEST)})
        returned = self.cases["response_verified"][1]
        self.assertEqual(returned["request_hops_before_loss"], 6)
        self.assertEqual(returned["wire"]["response"], RESPONSE_MARK)
        for _, result in self.cases.values():
            for scope in JOBS:
                self.assertEqual(result["final_job_accounting"][scope]["active"], 0)
                self.assertEqual(result["final_job_accounting"][scope]["members"], [])

    def test_unplanned_controller_loss_is_unavailable_and_recovers(self):
        _, result = run_case("normal", unexpected_loss=True)
        self.assertEqual(result["outcome"], "unavailable")
        self.assertTrue(result["valid"] and result["bounded_recovery"] and result["witness_finalized"])
        self.assertEqual(result["exit_codes"], {"controller": INJECTED_EXIT})
        self.assertEqual(result["fixture_eof"], "unavailable")
        self.assertTrue(all(job["active"] == 0 for job in result["final_job_accounting"].values()))

    def test_controller_launch_constraint_rejects_external_programs_and_roles(self):
        with self.assertRaises(ValueError):
            fixed_actor_command("synthetic-unsanctioned.exe", "discarded")
        with self.assertRaises(ValueError):
            fixed_actor_command(sys.executable, "unlisted entry point")

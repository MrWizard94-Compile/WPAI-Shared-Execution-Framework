from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qualification import EXPECTED, qualify
from witness_record import read_events, validate
from observer import observe


class SyntheticQualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = qualify()

    def test_normal_shutdown_correlates_independent_eof_and_exit(self):
        result = self.results["normal"]
        self.assertEqual(result["status"], "observed_success")
        self.assertEqual(result["observed_exit_codes"], {"wrapper": 0, "server": 0})
        self.assertEqual(result["stdin_eof_sources"], {"wrapper": "trusted_fixture_control_pipe",
                                                     "server": "trusted_fixture_control_pipe"})
        self.assertEqual(result["stdout_classification"], dict.fromkeys(("wrapper", "server"), "graceful_eof_observed"))
        self.assertEqual(result["job_accounting"]["final"], {"active": 0, "total": 2})
        self.assertTrue(result["observer_outside_target_job"])
        self.assertTrue(result["observer_finalized"])
        self.assertEqual(result["missing_observations"], [])

    def test_server_natural_zero_and_nonzero_are_separate(self):
        clean, failed = (self.results[name] for name in ("server_zero", "server_nonzero"))
        self.assertEqual(clean["observed_exit_codes"]["server"], 0)
        self.assertEqual(clean["status"], "observed_success")
        self.assertEqual(failed["observed_exit_codes"]["server"], 7)
        self.assertEqual(failed["status"], "observed_failure")
        self.assertEqual(failed["stdout_classification"]["server"], "graceful_eof_observed")

    def test_wrapper_death_leaves_server_active_until_later_cleanup(self):
        result = self.results["wrapper_only"]
        self.assertEqual(result["active_after_wrapper_exit"], ["server"])
        self.assertEqual(result["job_accounting"]["after_wrapper_exit"], {"active": 1, "total": 2})
        self.assertEqual(result["observed_exit_codes"], {"wrapper": 1, "server": 124})
        self.assertEqual(result["job_accounting"]["final"]["active"], 0)

    def test_real_wrapper_and_server_killed_before_receipt(self):
        actual = self.results["external_tree"]
        self.assertFalse(actual["in_band_receipt_present"])
        self.assertEqual(actual["observed_exit_codes"], {"wrapper": 124, "server": 124, "owner": 1})
        self.assertEqual(actual["force_requests"], {"job": "external_owner", "owner": "observer_control"})
        self.assertTrue(actual["external_owner_acknowledged"])
        self.assertEqual(actual["registered_processes"]["server"],
                         {"source": "bounded_job_membership", "in_job": True})
        self.assertFalse(actual["registered_processes"]["owner"]["in_job"])
        self.assertTrue(actual["observer_outside_target_job"])
        self.assertTrue(actual["observer_finalized"])
        self.assertEqual(actual["job_accounting"]["final"], {"active": 0, "total": 2})
        self.assertEqual(actual["status"], "observed_failure")
        self.assertEqual(actual["stdin_eof_sources"], {})
        self.assertIn("server.stdout_observation", actual["missing_observations"])
        self.assertEqual(actual["stdout_classification"]["wrapper"], "peer_closure_observed_after_force_request")
        self.assertEqual(actual["pipe_terminals"]["wrapper_stdout"],
                         {"outcome": "peer_closed", "source": "ReadFile", "winerror": 109})

    def test_real_descendant_outlives_the_root(self):
        result = self.results["descendant"]
        self.assertEqual(result["observed_exit_codes"]["wrapper"], 0)
        self.assertEqual(result["active_after_wrapper_exit"], ["descendant"])
        self.assertEqual(result["job_accounting"]["after_wrapper_exit"], {"active": 2, "total": 3})
        self.assertEqual(result["observed_exit_codes"]["descendant"], 124)
        self.assertEqual(result["job_accounting"]["final"], {"active": 0, "total": 3})

    def test_local_reader_closure_does_not_claim_a_pipe_read(self):
        result = self.results["local_pipe_close"]
        self.assertEqual(result["stdout_classification"]["server"], "local_close")
        self.assertEqual(result["pipe_terminals"]["server_stdout"],
                         {"outcome": "local_close", "source": "observer_closed_reader", "winerror": 0})
        self.assertNotIn("server", result["stdin_eof_sources"])
        self.assertEqual(result["status"], "observed_failure")

    def test_channel_disconnect_does_not_supply_stdin_eof(self):
        result = self.results["channel_broken"]
        self.assertEqual(result["pipe_terminals"]["server_control"]["outcome"], "peer_closed")
        self.assertEqual(result["observed_exit_codes"]["server"], 0)
        self.assertIn(["unavailable", "channel_disconnected"], result["issues"])
        self.assertIn("server.stdin_eof", result["missing_observations"])
        self.assertEqual(result["status"], "unavailable")

    def test_observer_crash_leaves_only_incomplete_evidence(self):
        result = self.results["observer_crash"]
        self.assertFalse(result["observer_finalized"])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["test_parent_after_observer_exit"], {"observer_exit_code": 91, "active": 0})
        self.assertEqual(result["observed_exit_codes"], {})

    def test_missing_registration_and_missing_code_are_distinct(self):
        unregistered, no_exit = (self.results[name] for name in ("missing_registration", "missing_exit"))
        self.assertIn("server.registration", unregistered["missing_observations"])
        self.assertNotIn("server", unregistered["signaled_processes"])
        self.assertEqual(unregistered["job_accounting"]["final"], {"active": 0, "total": 2})
        self.assertIn("server", no_exit["signaled_processes"])
        self.assertNotIn("server", no_exit["observed_exit_codes"])
        self.assertIn("server.exit_code", no_exit["missing_observations"])
        self.assertEqual(no_exit["status"], "unavailable")

    def test_same_pid_with_wrong_creation_identity_is_invalid(self):
        result = self.results["identity_mismatch"]
        self.assertIn(["invalid", "identity_mismatch"], result["issues"])
        self.assertEqual(result["status"], "invalid")

    def test_timeout_is_bounded_and_does_not_fake_natural_exit(self):
        result = self.results["timeout"]
        self.assertIn(["failure", "timeout"], result["issues"])
        self.assertEqual(result["observed_exit_codes"]["server"], 124)
        self.assertEqual(result["job_accounting"]["final"]["active"], 0)
        self.assertTrue(result["observer_finalized"])

    def test_all_normalized_scenarios_reproduce_exactly(self):
        self.assertEqual({key: result["status"] for key, result in self.results.items()}, EXPECTED)
        self.assertEqual(qualify(), self.results)

    def test_case_evidence_contains_incremental_independent_sources(self):
        with TemporaryDirectory() as path:
            record = Path(path) / "run.jsonl"
            observe("external_tree", record)
            events, unfinished = read_events(record)
            self.assertFalse(unfinished)
            self.assertEqual(len({event["run_id"] for event in events}), 1)
            self.assertEqual(events[0]["data"]["identity"], events[-1]["data"]["identity"])
            ordering = [event["kind"] for event in events]
            self.assertLess(ordering.index("force_requested"), ordering.index("process_exit"))
            self.assertLess(ordering.index("process_exit"), ordering.index("observer_finalized"))
            self.assertEqual(validate(record)["status"], "observed_failure")


if __name__ == "__main__":
    unittest.main()

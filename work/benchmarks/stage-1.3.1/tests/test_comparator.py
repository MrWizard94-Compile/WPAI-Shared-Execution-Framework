from copy import deepcopy
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparator import compare_pair, reconcile, report
from evidence import ARCHIVE, SOURCE, read


OMITTED = object()


class Telemetry(unittest.TestCase):
    def setUp(self):
        self.oracle = read(SOURCE / "ground_truth.json")
        self.control = read(ARCHIVE / "runs" / "codex-control.json")
        self.treatment = read(ARCHIVE / "runs" / "codex-treatment.json")

    def outcome(self, field, value):
        treatment = deepcopy(self.treatment)
        if value is OMITTED:
            treatment.pop(field)
        else:
            treatment[field] = value
        pair = compare_pair(self.control, treatment, self.oracle, archived=True)
        result = pair["treatment"]
        self.assertTrue(result["answer_valid"])
        self.assertFalse(result["tool_execution_valid"])
        self.assertFalse(result["pair_eligible"])
        self.assertFalse(pair["pair_eligible"])
        self.assertFalse(pair["resource_metrics_eligible"])
        self.assertEqual(pair["eligible_reduction_fractions"], {})
        self.assertEqual(pair["historical_observed_reduction_fractions"], {})
        return result

    def check_event_collection(self, field, value, status, count):
        result = self.outcome(f"client_tool_{field}", value)
        name = "start" if field == "starts" else "result"
        fixture_count = "start" if field == "starts" else "completion"
        self.assertEqual(result[f"client_tool_{field}_status"], status)
        self.assertEqual(result[f"client_tool_{name}_event_count"], count)
        self.assertEqual(result[f"client_fixture_{fixture_count}_count"], count)

    def test_starts_omitted(self):
        self.check_event_collection("starts", OMITTED, "unavailable", None)

    def test_starts_null(self):
        self.check_event_collection("starts", None, "unavailable", None)

    def test_starts_wrong_type(self):
        self.check_event_collection("starts", {}, "invalid", None)

    def test_results_omitted(self):
        self.check_event_collection("results", OMITTED, "unavailable", None)

    def test_results_null(self):
        self.check_event_collection("results", None, "unavailable", None)

    def test_results_wrong_type(self):
        self.check_event_collection("results", "completed", "invalid", None)

    def test_empty_arrays_are_observed_zero(self):
        for key in ("starts", "results"):
            with self.subTest(key=key):
                self.check_event_collection(key, [], "observed", 0)
        result = self.outcome("server_trace", [])
        self.assertEqual(result["server_trace_status"], "observed")
        self.assertEqual(result["server_trace_event_count"], 0)
        self.assertEqual(result["server_operation_count"], 0)

    def test_valid_nonmatching_events_are_observed_zero_matches(self):
        started = self.outcome("client_tool_starts", [{"is_fixture": False, "status": "in_progress"}])
        self.assertEqual(started["client_tool_starts_status"], "observed")
        self.assertEqual(started["client_tool_start_event_count"], 1)
        self.assertEqual(started["client_fixture_start_count"], 0)
        self.assertTrue(started["expected_client_tool_completions_observed"])
        completed = self.outcome("client_tool_results", [{"is_fixture": True, "status": "cancelled", "has_result": False}])
        self.assertEqual(completed["client_tool_results_status"], "observed")
        self.assertEqual(completed["client_tool_result_event_count"], 1)
        self.assertEqual(completed["client_fixture_completion_count"], 0)

    def test_malformed_elements_invalidate_whole_collection(self):
        for key in ("starts", "results"):
            original = self.treatment[f"client_tool_{key}"]
            for member in (None, [], "started", {}, {"is_fixture": 1}, {"is_fixture": True, "status": []}):
                with self.subTest(key=key, member=member):
                    self.check_event_collection(key, [*original, member], "invalid", None)
        missing_result_fields = [{"is_fixture": True, "status": "completed"}]
        self.check_event_collection("results", missing_result_fields, "invalid", None)

    def test_extra_starts_and_missing_completions(self):
        self.treatment["client_tool_starts"] *= 2
        result = self.outcome("client_tool_results", [])
        self.assertEqual(result["client_fixture_start_count"], 2)
        self.assertEqual(result["client_fixture_completion_count"], 0)
        self.assertFalse(result["expected_client_tool_starts_observed"])
        self.assertFalse(result["expected_client_tool_completions_observed"])

    def test_completion_without_corresponding_start(self):
        result = self.outcome("client_tool_starts", [])
        self.assertEqual(result["client_fixture_start_count"], 0)
        self.assertEqual(result["client_fixture_completion_count"], 1)
        self.assertFalse(result["expected_tool_execution_observed"])

    def test_out_of_scope_collection_status_and_count(self):
        for value, status, count in ((OMITTED, "unavailable", None), (None, "unavailable", None),
                                     ({}, "invalid", None), ([None], "invalid", None),
                                     (["extra"], "observed", 1)):
            with self.subTest(status=status, value=value):
                result = self.outcome("out_of_scope_tool_events", value)
                self.assertEqual(result["out_of_scope_tool_events_status"], status)
                self.assertEqual(result["out_of_scope_tool_event_count"], count)
        result = reconcile(self.treatment, self.oracle, archived=True)
        self.assertEqual(result["out_of_scope_tool_events_status"], "observed")
        self.assertEqual(result["out_of_scope_tool_event_count"], 0)
        self.assertTrue(result["tool_execution_valid"])

    def test_missing_null_and_malformed_server_trace(self):
        for value, status in ((OMITTED, "unavailable"), (None, "unavailable"), ({}, "invalid"), ([None], "invalid"),
                              ([{}], "invalid"), ([{"event": []}], "invalid"),
                              ([*self.treatment["server_trace"], {"event": "stop", "code": True}], "invalid")):
            with self.subTest(status=status):
                result = self.outcome("server_trace", value)
                self.assertEqual(result["server_trace_status"], status)
                self.assertIsNone(result["server_trace_event_count"])
                self.assertIsNone(result["server_operation_count"])
                self.assertIsNone(result["failed_or_unanswered_server_operations"])
                self.assertIsNone(result["server_stop_events"])
                self.assertFalse(result["protocol_identity_valid"])

    def test_missing_null_and_malformed_client_process(self):
        for value, status in ((OMITTED, "unavailable"), (None, "unavailable"), ([], "invalid"), ({}, "invalid"),
                              ({"exit_code": True, "forced": False}, "invalid"),
                              ({"exit_code": 0, "forced": 0}, "invalid")):
            with self.subTest(status=status):
                result = self.outcome("client_process", value)
                self.assertEqual(result["client_process_status"], status)
                self.assertFalse(result["client_exit_zero_unforced"])

    def test_historical_results_and_lifecycle_gates_are_preserved(self):
        archive = read(ARCHIVE / "comparison.json")
        current = report()
        for provider, pair in current["providers"].items():
            self.assertEqual(pair["historical_observed_reduction_fractions"], archive[provider]["observed_reduction_fractions"])
            self.assertEqual(pair["pair_eligible"], archive[provider]["matched_and_accurate"])
            self.assertFalse(pair["resource_metrics_eligible"])
            for arm in ("control", "treatment"):
                slot = pair[arm]
                self.assertEqual(slot["lifecycle_status"], "open")
                self.assertIsNone(slot["pump_threads_started"])
                for metric in ("actual_billable_api_charge_usd", "subscription_quota_delta", "model_only_latency_seconds",
                               "tool_call_rounds"):
                    self.assertIsNone(slot["metrics"][metric])
        self.assertFalse(current["providers"]["grok"]["pair_eligible"])
        agy_control = read(ARCHIVE / "runs" / "antigravity-control.json")
        agy_control["client_observed_result_bytes"] = 123
        result = reconcile(agy_control, self.oracle, archived=True)
        self.assertIsNone(result["client_observed_result_bytes"])
        self.assertFalse(result["client_observed_result_bytes_available"])
        self.assertTrue(result["expected_client_tool_completions_observed"])


if __name__ == "__main__":
    unittest.main()

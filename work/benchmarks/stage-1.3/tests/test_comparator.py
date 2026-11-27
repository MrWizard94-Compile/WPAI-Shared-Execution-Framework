from copy import deepcopy
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparator import compare_pair, reconcile, report
from evidence import ARCHIVE, IDENTITIES, SOURCE, TOOLS, parse, read
from paired_stats import summarize


class Comparator(unittest.TestCase):
    def setUp(self):
        self.oracle = read(SOURCE / "ground_truth.json")
        self.control, self.treatment = (read(ARCHIVE / "runs" / f"codex-{arm}.json") for arm in TOOLS)

    def qualify(self, record, index=0):
        record["run_id"] = f"{2 * index + (1 if record['arm'] == 'control' else 2):032x}"
        record["fixture_identities"] = dict(IDENTITIES)
        record["lifecycle"] = {
            "schema": "wpai.benchmark.lifecycle.v1", "client_stdin_eof": True,
            "child_stdin_closed": True, "server_eof_observed": True, "server_exit_code": 0,
            "forced_termination": False, "process_tree_verified_gone": True, "processes_in_owned_job": 1,
            "active_processes_at_check": 0, "transport_ok": True, "transport_faults": [],
            "termination_reason": "child_exited",
            "run_id": record["run_id"], "arm": record["arm"], "fixture_identities": dict(IDENTITIES),
        }

    def test_stage_1_2_reductions_and_attempts_reconciled(self):
        data = report()
        legacy = read(ARCHIVE / "comparison.json")
        for provider, pair in data["providers"].items():
            self.assertEqual(pair["historical_observed_reduction_fractions"], legacy[provider]["observed_reduction_fractions"])
            for arm in TOOLS:
                self.assertTrue(pair[arm]["answer_valid"])
                self.assertEqual(pair[arm]["exact_fields"], 12)
                self.assertTrue(pair[arm]["expected_tool_execution_observed"])
                self.assertEqual(pair[arm]["lifecycle_status"], "open")
                self.assertIsNone(pair[arm]["server_exit_code"])
            self.assertFalse(pair["resource_metrics_eligible"])
        self.assertFalse(data["providers"]["grok"]["control"]["tool_execution_valid"])
        self.assertFalse(data["providers"]["grok"]["pair_eligible"])
        self.assertEqual(data["providers"]["grok"]["control"]["out_of_scope_tool_activity"],
                         ["unqualified_or_unapproved_search_tool"])
        agy = data["providers"]["antigravity"]["control"]
        self.assertEqual(agy["archived_server_application_exit_code"], 0)
        self.assertIsNone(agy["client_observed_result_bytes"])
        self.assertEqual(agy["client_tool_result_events_with_result"], 0)
        self.assertTrue(agy["exact_reply_digests_valid"])
        self.assertEqual(len(data["discarded_attempts"]), 6)
        attempt = data["discarded_attempts"]["antigravity-treatment.json"]
        self.assertEqual(attempt["disposition"], "discarded")
        self.assertEqual(attempt["permission_decisions"], ["cancelled"])
        self.assertFalse(attempt["tool_execution_valid"])
        self.assertEqual(len(data["source_record_sha256"]), 12)

    def test_exact_answer_independent_of_trace_and_score(self):
        for mutated in (True, 2.0, "2"):
            record = deepcopy(self.control)
            record["validated_answer"]["facts"]["05_change_counts"]["value"]["staged"] = mutated
            result = reconcile(record, self.oracle)
            self.assertTrue(result["tool_execution_valid"])
            self.assertFalse(result["answer_valid"])
            self.assertEqual(result["exact_fields"], 11)
        self.control["final_response_received"] = False
        self.assertFalse(reconcile(self.control, self.oracle)["answer_valid"])

    def test_missing_or_failed_activity_fails_closed(self):
        for action in ("missing_completion", "extra_start", "bad_digest", "bad_parity", "failed_operation",
                       "unexpected_request", "wrong_tool", "unreported_scope", "protocol", "server_failed",
                       "blocked", "incomplete_run"):
            with self.subTest(action=action):
                record = deepcopy(self.treatment)
                trace = record["server_trace"]
                reply = next(row for row in trace if row.get("event") == "sent" and row.get("method") == "tools/call")
                operation = next(row for row in trace if row.get("event") == "acquisition")
                if action == "missing_completion":
                    record["client_tool_results"].clear()
                elif action == "extra_start":
                    record["client_tool_starts"].append({"is_fixture": False})
                elif action == "bad_digest":
                    reply["report_sha256"] = "0" * 64
                elif action == "bad_parity":
                    reply["parity"] = 1
                elif action == "failed_operation":
                    trace.extend(({"event": "received", "method": "tools/call"},
                                  {"event": "acquisition", "status": "DENIED"},
                                  {"event": "sent", "method": "tools/call", "ok": False}))
                elif action == "unexpected_request":
                    trace.append({"event": "received", "method": "tools/call"})
                elif action == "wrong_tool":
                    operation["tool"] = "other"
                elif action == "unreported_scope":
                    del record["out_of_scope_tool_events"]
                elif action == "protocol":
                    reply["protocol"] = "2026-07-28"
                elif action == "server_failed":
                    trace.append({"event": "stop", "code": 1, "worker_alive": False})
                elif action == "blocked":
                    record["blocked"] = "permission_matching_failed"
                else:
                    record["stop_reason"] = "cancelled"
                result = compare_pair(self.control, record, self.oracle, archived=True)
                self.assertTrue(result["treatment"]["answer_valid"])
                self.assertFalse(result["pair_eligible"])
                self.assertEqual(result["historical_observed_reduction_fractions"], {})

    def test_frozen_protocol_identity_and_matching_settings(self):
        for key in ("client_version", "model", "reasoning_setting", "auth_category"):
            candidate = deepcopy(self.treatment)
            candidate[key] = "different"
            pair = compare_pair(self.control, candidate, self.oracle, archived=True)
            self.assertFalse(pair["pair_eligible"])
        self.treatment["prompt_sha256"] = self.control["prompt_sha256"]
        self.assertFalse(compare_pair(self.control, self.treatment, self.oracle, archived=True)["pair_eligible"])

    def test_native_receipt_required_for_future_resource_claim(self):
        pending = compare_pair(self.control, self.treatment, self.oracle)
        self.assertFalse(pending["pair_eligible"])
        self.assertNotIn("historical_observed_reduction_fractions", pending)
        for run in (self.control, self.treatment):
            self.qualify(run)
        pair = compare_pair(self.control, self.treatment, self.oracle)
        self.assertTrue(pair["resource_metrics_eligible"])
        self.assertFalse(pair["metric_eligibility"]["model_calls"])
        self.assertFalse(pair["metric_eligibility"]["provider_reported_cost_usd"])
        for patch in ({"server_exit_code": False}, {"forced_termination": True}, {"active_processes_at_check": 1},
                      {"server_eof_observed": None}, {"transport_faults": ["stdout_pipe_error"]},
                      {"run_id": "3" * 32}, {"arm": "control"}):
            candidate = deepcopy(self.treatment)
            candidate["lifecycle"].update(patch)
            result = compare_pair(self.control, candidate, self.oracle)
            self.assertFalse(result["treatment"]["lifecycle_valid"])
            self.assertFalse(result["pair_eligible"])
        del self.treatment["fixture_identities"]["ground_truth.json"]
        self.assertFalse(compare_pair(self.control, self.treatment, self.oracle)["resource_metrics_eligible"])

    def test_nonfinite_and_boolean_telemetry(self):
        for invalid in ("1e9999", "NaN", "Infinity", '{"x":0,"x":1}'):
            with self.assertRaises(ValueError):
                parse(invalid)
        for value in (True, float("inf"), -1, None):
            record = deepcopy(self.control)
            record["usage"]["input_tokens"] = value
            result = reconcile(record, self.oracle)
            self.assertIsNone(result["metrics"]["total_tokens"])
            self.assertTrue(result["usage_telemetry_available"])

    def test_paired_descriptives_allow_increases_and_missing_data(self):
        for run in (self.control, self.treatment):
            self.qualify(run)
        pairs = []
        for index, (left, right) in enumerate(((10, 2), (4, 8), (0, 2), (None, 2), (5, 1))):
            control, treatment = deepcopy((self.control, self.treatment))
            self.qualify(control, index)
            self.qualify(treatment, index)
            control["model_calls"], treatment["model_calls"] = left, right
            if index == 4:
                control["out_of_scope_tool_events"] = ["extra"]
            pairs.append({"pair_id": str(index), "control": control, "treatment": treatment})
        metric = summarize("codex", pairs, self.oracle)["metrics"]["model_calls"]
        self.assertEqual(metric["missing_control"], 1)
        self.assertEqual(metric["present_but_ineligible"], 1)
        self.assertEqual(metric["eligible_zero_denominator"], 1)
        self.assertEqual(metric["distributions"]["difference_control_minus_treatment"],
                         {"count": 3, "median": -2, "minimum": -4, "maximum": 8})
        self.assertAlmostEqual(metric["distributions"]["reduction_fraction"]["median"], -0.1)
        with self.assertRaises(ValueError):
            summarize("grok", pairs, self.oracle)
        with self.assertRaises(ValueError):
            summarize("codex", [pairs[0], {**pairs[0], "pair_id": "other"}], self.oracle)


if __name__ == "__main__":
    unittest.main()

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from comparator import compare_pair, reconcile
from evidence import ARCHIVE, IDENTITIES, SOURCE, read
from lifecycle_receipt import SCHEMA, merge_receipt
from paired_stats import summarize


def clean_receipt(run):
    return {
        "schema": SCHEMA, "arm": run["arm"], "run_id": run["run_id"], "fixture_identities": dict(IDENTITIES),
        "client_stdin_eof": True, "child_stdin_closed": True, "server_eof_observed": True, "server_exit_code": 0,
        "forced_termination": False, "termination_reason": "child_exited", "process_tree_verified_gone": True,
        "processes_in_owned_job": 1, "active_processes_at_check": 0, "pump_threads_started": 3,
        "pump_threads_stopped": 3, "pump_threads_verified_stopped": True, "outstanding_pump_threads": [],
        "transport_ok": True, "transport_faults": [], "transport_fault_winerrors": {}, "lifecycle_valid": True,
    }


class Receipt(unittest.TestCase):
    def setUp(self):
        self.oracle = read(SOURCE / "ground_truth.json")
        self.control, self.treatment = (read(ARCHIVE / "runs" / f"codex-{arm}.json") for arm in ("control", "treatment"))
        self.control.update(run_id="1" * 32, fixture_identities=dict(IDENTITIES))
        self.treatment.update(run_id="2" * 32, fixture_identities=dict(IDENTITIES))
        self.receipt = clean_receipt(self.treatment)

    def test_merge_preserves_original_fields_and_validates_strict_future_pair(self):
        before_run = deepcopy(self.treatment)
        before_receipt = deepcopy(self.receipt)
        merged = merge_receipt(self.treatment, self.receipt)
        self.assertIs(merged["lifecycle"], self.receipt)
        self.assertEqual({key: value for key, value in merged.items() if key != "lifecycle"}, before_run)
        self.assertEqual(self.treatment, before_run)
        self.assertEqual(self.receipt, before_receipt)
        outcomes = compare_pair(merge_receipt(self.control, clean_receipt(self.control)), merged, self.oracle)
        self.assertTrue(outcomes["treatment"]["lifecycle_valid"])
        self.assertTrue(outcomes["treatment"]["tool_execution_valid"])
        self.assertTrue(outcomes["pair_eligible"])
        self.assertTrue(outcomes["resource_metrics_eligible"])
        self.assertFalse(outcomes["metric_eligibility"]["model_calls"])
        self.assertFalse(outcomes["metric_eligibility"]["provider_reported_cost_usd"])
        summary = summarize("codex", [{"pair_id": "synthetic-01", "control": merge_receipt(
            self.control, clean_receipt(self.control)), "treatment": merged}], self.oracle)
        self.assertEqual(summary["metrics"]["server_operation_count"]["distributions"][
            "difference_control_minus_treatment"]["median"], 11)

    def assert_rejected(self, receipt, reason):
        with self.assertRaisesRegex(ValueError, reason):
            merge_receipt(self.treatment, receipt)
        outcome = reconcile({**self.treatment, "lifecycle": receipt}, self.oracle)
        self.assertEqual(outcome["lifecycle_receipt_status"], "invalid")
        self.assertFalse(outcome["lifecycle_valid"])
        self.assertFalse(outcome["pair_eligible"])
        self.assertFalse(outcome["resource_metrics_eligible"])

    def test_mismatched_run_id(self):
        self.assert_rejected({**self.receipt, "run_id": self.control["run_id"]}, "run ID")

    def test_mismatched_arm(self):
        self.assert_rejected({**self.receipt, "arm": "control"}, "arm mismatch")

    def test_mismatched_fixture_identities(self):
        self.assert_rejected({**self.receipt, "fixture_identities": {}}, "fixture identity")
        self.treatment["fixture_identities"] = {}
        self.assert_rejected(self.receipt, "fixture identity")

    def test_duplicate_and_conflicting_receipts_are_rejected(self):
        for existing in (None, self.receipt, clean_receipt(self.control)):
            with self.subTest(existing_present=existing is not None):
                with self.assertRaisesRegex(ValueError, "already has"):
                    merge_receipt({**self.treatment, "lifecycle": existing}, self.receipt)

    def test_v1_and_inconsistent_pump_proofs_fail_closed(self):
        self.assert_rejected({**self.receipt, "schema": "wpai.benchmark.lifecycle.v1"}, "v2")
        for changed in (
            {"pump_threads_stopped": 2}, {"pump_threads_verified_stopped": False}, {"pump_threads_started": True},
            {"outstanding_pump_threads": ["stdout"]}, {"transport_fault_winerrors": {"stdout_cancel_error": 5}},
            {"pump_threads_started": 2, "pump_threads_stopped": 2},
        ):
            with self.subTest(changed=changed):
                self.assert_rejected({**self.receipt, **changed}, "pump|Windows fault")

    def test_associated_failed_receipt_retains_a_pump_even_after_the_tree_is_gone(self):
        failed = {**self.receipt, "pump_threads_stopped": 2, "pump_threads_verified_stopped": False,
                  "outstanding_pump_threads": ["stdout"], "transport_ok": False,
                  "transport_faults": ["stdout_thread_still_alive"], "lifecycle_valid": False}
        merged = merge_receipt(self.treatment, failed)
        outcome = reconcile(merged, self.oracle)
        self.assertEqual(outcome["lifecycle_receipt_status"], "observed")
        self.assertTrue(outcome["process_tree_verified_gone"])
        self.assertTrue(outcome["answer_valid"])
        self.assertTrue(outcome["tool_execution_valid"])
        self.assertFalse(outcome["lifecycle_valid"])
        self.assertEqual(outcome["outstanding_pump_threads"], ["stdout"])
        self.assertFalse(outcome["resource_metrics_eligible"])

    def test_real_synthetic_wrapper_receipt_merges_via_cli(self):
        with TemporaryDirectory() as directory:
            location = Path(directory)
            receipt_file, run_file, merged_file = (location / f"{name}.json" for name in ("receipt", "run", "merged"))
            run = {"provider": "codex", "arm": "treatment", "run_id": "3" * 32, "fixture_identities": IDENTITIES,
                   "client_process": {"exit_code": 0, "forced": False}}
            raw = json.dumps(run).encode()
            run_file.write_bytes(raw)
            argv = [sys.executable, "-B", "-W", "error"]
            wrapper = subprocess.run([*argv, str(HERE / "wrapper.py"), "treatment", "--record", str(receipt_file),
                                      "--run-id", run["run_id"]], input=b"", capture_output=True, timeout=10, check=True)
            self.assertEqual(wrapper.stdout, b"")
            self.assertEqual(wrapper.stderr, b"")
            receipt_bytes = receipt_file.read_bytes()
            subprocess.run([*argv, str(HERE / "lifecycle_receipt.py"), str(run_file), str(receipt_file),
                            "--output", str(merged_file)], capture_output=True, timeout=10, check=True)
            merged = read(merged_file)
            self.assertEqual(merged["lifecycle"], json.loads(receipt_bytes))
            self.assertEqual(run_file.read_bytes(), raw)
            self.assertEqual(receipt_file.read_bytes(), receipt_bytes)
            outcome = reconcile(merged, self.oracle)
            self.assertTrue(outcome["lifecycle_valid"])
            self.assertFalse(outcome["tool_execution_valid"])
            self.assertFalse(outcome["pair_eligible"])
            self.assertEqual(outcome["pump_threads_stopped"], 3)


if __name__ == "__main__":
    unittest.main()

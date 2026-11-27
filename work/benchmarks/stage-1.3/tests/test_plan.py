from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from evidence import IDENTITIES, ROUTES, TOOLS
from plan import DEFAULT_SEED, make_plan, order_for, validate


class Plan(unittest.TestCase):
    def setUp(self):
        self.plan = make_plan()

    def test_default_command_and_explicit_plan_only_have_no_process_or_network_calls(self):
        blocked = ("subprocess.Popen", "subprocess.run", "os.system", "os.startfile",
                   "os.spawnv", "os.execv", "_winapi.CreateProcess", "socket.socket", "socket.create_connection")
        outputs = []
        for args in ([], ["--plan-only", "--seed", str(DEFAULT_SEED)]):
            capture = StringIO()
            with ExitStack() as stack:
                for name in blocked:
                    stack.enter_context(patch(name, side_effect=AssertionError(f"{name} must not run")))
                stack.enter_context(patch.object(sys, "argv", [str(HERE / "plan.py"), *args]))
                stack.enter_context(redirect_stdout(capture))
                runpy.run_path(str(HERE / "plan.py"), run_name="__main__")
            outputs.append(capture.getvalue())
        self.assertEqual(*outputs)
        self.assertEqual(json.loads(outputs[0]), self.plan)

    def test_seed_reproducibility_and_balance(self):
        self.assertEqual(make_plan(DEFAULT_SEED), self.plan)
        for route in ROUTES:
            distinct = set()
            for seed in range(20):
                order = order_for(seed, route)
                self.assertTrue(all(set(pair) == set(TOOLS) for pair in order))
                self.assertIn(sum(pair[0] == "control" for pair in order), (2, 3))
                distinct.add(tuple(order))
            self.assertGreater(len(distinct), 5)
        self.assertNotEqual(make_plan(0)["routes"], self.plan["routes"])

    def test_session_budgets_fingerprints_and_fresh_contexts(self):
        self.assertEqual(self.plan["session_counts"], {
            "authorized_now": 0, "historically_matched_routes_if_qualified": 20,
            "all_three_routes_if_qualified": 30, "includes_qualification_sessions": False})
        alternative = make_plan(0)
        fresh = set()
        for provider, route in self.plan["routes"].items():
            self.assertEqual(route["paired_runs"], 5)
            self.assertEqual(route["model_sessions"], 10)
            self.assertFalse(route["ready_for_live_resource_comparison"])
            for arm, config in route["configurations"].items():
                self.assertEqual(config, alternative["routes"][provider]["configurations"][arm])
                self.assertEqual(config["settings"]["fixture"], IDENTITIES)
                self.assertTrue(config["settings"]["fresh_context"])
            for pair in route["pairs"]:
                fresh.update(run["context_id"] for run in pair["run_order"])
        self.assertEqual(len(fresh), 30)
        self.assertIn("out_of_scope_control_requalification", self.plan["routes"]["grok"]["open_gates"])

    def test_reject_fingerprint_or_order_mutation(self):
        for field in ("configuration", "order"):
            broken = deepcopy(self.plan)
            route = broken["routes"]["codex"]
            if field == "configuration":
                route["configurations"]["control"]["settings"]["tool"] = "unexpected_tool"
            else:
                route["pairs"][0]["run_order"].reverse()
            with self.assertRaises(ValueError):
                validate(broken)
        with self.assertRaises(ValueError):
            make_plan(-1)


if __name__ == "__main__":
    unittest.main()

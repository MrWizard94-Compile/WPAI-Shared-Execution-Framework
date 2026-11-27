"""Exercise Stage 1.5 boundaries without launching any process or provider."""

from copy import deepcopy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from route_matrix import OUTPUT, PROVIDERS, render, validate_matrix, validate_public_text


class RouteMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads(render())

    def test_reproduces_published_bytes(self):
        self.assertEqual(render(), render())
        self.assertEqual(render(), (OUTPUT / "route-matrix.json").read_bytes())

    def test_exact_providers_and_frozen_counts(self):
        self.assertEqual(set(self.matrix["routes"]), set(PROVIDERS))
        self.assertEqual(self.matrix["frozen_repeatability"]["paired_runs"], dict.fromkeys(PROVIDERS, 5))
        self.assertEqual(self.matrix["future_sessions_if_all_authorized"], 6)
        self.assertEqual(self.matrix["authorized_now"], 0)
        self.assertEqual(self.matrix["live_provider_sessions_started"], 0)
        self.assertIs(self.matrix["live_inference_authorized"], False)

    def test_processes_are_explicit_and_distinct(self):
        codex = {layer["id"]: layer for layer in self.matrix["routes"]["codex"]["layers"]}
        agy = {layer["id"]: layer for layer in self.matrix["routes"]["antigravity"]["layers"]}
        grok = {layer["id"]: layer for layer in self.matrix["routes"]["grok"]["layers"]}
        self.assertEqual(codex["app_runtime"]["role"], "matched_in_process")
        self.assertEqual(agy["client"]["parent"], "acp_driver")
        self.assertEqual(agy["acp_worker"]["parent"], "UNKNOWN")
        self.assertEqual(grok["acp_alternative"]["role"], "excluded_historical_route")
        for route in self.matrix["routes"].values():
            self.assertIs(route["native_qualified"], False)
            self.assertEqual(route["authorized_sessions"], 0)
            self.assertEqual(route["readiness"], "NO-GO")

    def test_rejects_changed_authority_history_and_topology(self):
        changes = (
            lambda data: data.update(authorized_now=1),
            lambda data: data.update(live_inference_authorized=True),
            lambda data: data["routes"].pop("grok"),
            lambda data: data["routes"]["grok"].update(native_qualified=True),
            lambda data: data["routes"]["codex"]["layers"][2].update(parent="client"),
            lambda data: data["routes"]["antigravity"]["layers"][4].update(parent="client"),
            lambda data: data["routes"]["grok"]["observations"]["job_accounting"].update({"class": "direct"}),
            lambda data: data["frozen_repeatability"]["paired_runs"].update(codex=4),
            lambda data: data["routes"]["grok"].update(raw_configuration={}),
        )
        for change in changes:
            with self.subTest(change=change):
                altered = deepcopy(self.matrix)
                change(altered)
                with self.assertRaises(ValueError):
                    validate_matrix(altered)

    def test_handoff_evidence_and_plan_have_no_private_values_or_session_commands(self):
        for path in OUTPUT.glob("*.md"):
            validate_public_text(path.read_text(encoding="utf-8"), plan=path.name == "qualification-plan.md")
        for text in ('"password": "' + "a" * 18 + '"', "Bearer " + "a" * 18, "C:" + r"\Users\test\config"):
            with self.assertRaises(ValueError):
                validate_public_text(text)
        for text in ("codex" + " exec task", "agy" + " acp --flag", "grok" + " -p task"):
            with self.assertRaises(ValueError):
                validate_public_text(text, plan=True)

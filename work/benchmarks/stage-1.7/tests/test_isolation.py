"""Test static evidence and fail-closed authorization independently of golden bytes."""

from copy import deepcopy
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog import CODEX_SHA, GROK_BUILD, GROK_MIRROR
from isolation_matrix import OUTPUT, decode, guard_public, render, validate
from public_evidence import verify_history


def claim(matrix, route, identity):
    return next(item for item in matrix["routes"][route]["claims"] if item["id"] == identity)


class StaticIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = decode(render())

    def altered(self, mutation):
        data = deepcopy(self.data)
        mutation(data)
        with self.assertRaises(ValueError):
            validate(data)

    def test_deterministic_offline_reproduction(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network access")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("process launch")):
            self.assertEqual(render(), render())
            self.assertEqual(render(), (OUTPUT / "isolation-matrix.json").read_bytes())
            self.assertGreater(verify_history(), 0)

    def test_exact_route_ids_versions_and_fingerprints(self):
        routes = self.data["routes"]
        self.assertEqual(set(routes), {"codex", "antigravity", "grok"})
        self.assertEqual(routes["grok"]["version"]["build_marker"], GROK_BUILD)
        self.assertEqual(routes["codex"]["version"]["matched_source"], CODEX_SHA)
        self.assertIsNone(routes["antigravity"]["version"]["matched_source"])
        self.assertIsNone(routes["grok"]["version"]["matched_source"])
        self.altered(lambda data: data["routes"]["grok"]["version"].update(digest="0" * 64))

    def test_rolling_authentication_cannot_be_promoted(self):
        def promote(data):
            item = claim(data, "antigravity", "ag-auth-doc")
            item["class"] = "VERSION_MATCHED_OFFICIAL_DOC"
            item["source"].update(applicability="exact_version", revision="1.5.18")

        self.altered(promote)
        self.altered(lambda data: claim(data, "codex", "cx-file")["source"].update(revision="0" * 40))
        self.altered(lambda data: claim(data, "codex", "cx-file").update(version="0.166.1"))

    def test_unmatched_mirror_cannot_supply_pinned_source(self):
        def promote(data):
            item = claim(data, "grok", "gr-mirror")
            item["class"] = "VERSION_MATCHED_SOURCE"
            item["source"]["applicability"] = "exact_version"

        self.altered(promote)
        self.altered(lambda data: data["routes"]["grok"]["version"].update(matched_source=GROK_MIRROR))
        self.altered(lambda data: data["routes"]["antigravity"].update(provenance="matched_source"))

    def test_no_provider_can_clear_essential_gates_by_assertion(self):
        for name, route in self.data["routes"].items():
            with self.subTest(route=name):
                self.assertEqual(route["decision"], "NO-GO")
                self.assertFalse(route["future_preflight_eligible"])
                self.assertFalse(route["native_qualified"])
        self.altered(lambda data: data["routes"]["codex"].update(classification="PROVEN_ISOLATED"))
        self.altered(lambda data: data["routes"]["antigravity"]["essential_gates"]["ordinary_subscription"].update(
            status="established", claims=["ag-auth-doc"]))
        self.altered(lambda data: data["routes"]["codex"]["essential_gates"]["ordinary_subscription"].update(
            status="established", claims=["cx-file"]))

    def test_precedence_preserves_enforced_requirements_and_exact_edges(self):
        edges = self.data["routes"]["codex"]["precedence"]["exact_edges"]
        self.assertEqual(edges[-1]["higher"], "enforced_requirements")
        self.altered(lambda data: data["routes"]["codex"]["precedence"]["exact_edges"].append(
            {"lower": "runtime", "higher": "packaged", "claim": "cx-config"}))
        self.altered(lambda data: data["routes"]["codex"]["precedence"]["exact_edges"].append(
            {"lower": "enforced_requirements", "higher": "runtime", "claim": "cx-config"}))
        self.altered(lambda data: data["routes"]["grok"]["precedence"]["exact_edges"].append(
            {"lower": "user", "higher": "managed", "claim": "gr-policy-doc"}))

    def test_frozen_counts_and_authority_are_strict(self):
        self.assertEqual(self.data["frozen"]["proposed_lifecycle_cases"], 6)
        self.assertEqual(self.data["frozen"]["session_counts"]["all_three_routes_if_qualified"], 30)
        for name in self.data["authorization"]:
            self.altered(lambda data: data["authorization"].update({name: 1}))
        self.altered(lambda data: data["frozen"]["paired_runs"].update(grok=4))
        self.altered(lambda data: data["routes"]["grok"].update(authorized_sessions=1))
        self.altered(lambda data: data["routes"]["grok"].update(native_qualified=True))

    def test_public_data_and_strict_json_limits(self):
        for content in ("Bearer " + "a" * 24, "C:" + r"\Users\example\private.json",
                        '"password": "' + "a" * 18 + '"'):
            with self.assertRaises(ValueError):
                guard_public(content)
        with self.assertRaises(ValueError):
            decode(b'{"mode": 1, "mode": 2}')
        self.altered(lambda data: data["routes"]["codex"].update(raw_provider_profile={}))
        self.altered(lambda data: data["evidence_counts"].update(UNKNOWN=0))

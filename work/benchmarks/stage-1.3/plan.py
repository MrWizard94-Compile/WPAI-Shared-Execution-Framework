"""Print a validated, deterministic plan. This module has no execution mode."""

import argparse
import json

from comparator import report
from evidence import IDENTITIES, ROUTES, TOOLS, compact, digest


DEFAULT_SEED = 20261127
PAIR_COUNT = 5
AUTHORIZATION_GATE = [
    "Obtain explicit authorization for live inference, named providers, session budget and subscription use.",
    "Qualify each proposed native or independently owned transport for complete lifecycle evidence.",
    "Requalify Grok control with no out-of-scope tools before including the route in resource comparison.",
    "Confirm the exact client/model/settings and fixture fingerprints before starting a pair.",
    "Approve any qualification sessions separately. They are outside the five-pair counts.",
]
MEASUREMENTS = {
    "all_routes": ["model_calls", "agent_turns", "client_observed_benchmark_calls", "server_operation_count",
                   "raw_input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens",
                   "reasoning_tokens", "total_tokens", "whole_run_seconds_including_preflight",
                   "provider_phase_seconds", "server_call_round_trip_ms", "server_acquisition_ms",
                   "server_serialization_ms", "server_report_json_bytes", "server_rpc_wire_bytes",
                   "provider_reported_cost_usd", "lifecycle"],
    "unavailable_across_stage_1_2": ["actual_billable_api_charge_usd", "subscription_quota_delta",
                                     "model_only_latency_seconds", "tool_call_rounds", "client_observed_result_bytes"],
    "codex_unavailable": ["model_calls", "provider_phase_seconds", "provider_reported_cost_usd"],
    "antigravity_unavailable": ["model_calls", "provider_reported_cost_usd",
                                "input_tokens_including_known_cache", "separate_reasoning_setting"],
    "grok_provider_cost_is_billing": False,
}


def order_for(seed, provider):
    def key(label):
        return digest(compact(["wpai.paired-order.v1", seed, provider, label]))

    indices = sorted(range(1, PAIR_COUNT + 1), key=lambda index: (key(index), index))
    control_first_count = 2 + (int(key("arm-count"), 16) & 1)
    control_first = set(indices[:control_first_count])
    return [("control", "treatment") if index in control_first else ("treatment", "control")
            for index in range(1, PAIR_COUNT + 1)]


def validate(plan):
    if plan["execution_mode"] != "plan-only" or plan["live_inference_authorized"] is not False:
        raise ValueError("The plan must be offline")
    routes = plan["routes"]
    if set(routes) != set(ROUTES):
        raise ValueError("Expected exactly the three supported routes")
    for provider, route in routes.items():
        pairs = route["pairs"]
        expected_order = order_for(plan["seed"], provider)
        if (len(pairs) != PAIR_COUNT or not 2 <= sum(order[0] == "control" for order in expected_order) <= 3
                or route["model_sessions"] != 2 * PAIR_COUNT or set(route["configurations"]) != set(TOOLS)):
            raise ValueError(f"Invalid paired schedule for {provider}")
        for arm, config in route["configurations"].items():
            settings = config["settings"]
            if (config["sha256"] != digest(compact(settings, sort=True)) or settings["arm"] != arm
                    or settings["tool"] != TOOLS[arm] or settings["provider"] != provider
                    or settings["prompt_sha256"] != IDENTITIES[f"{arm}-prompt.txt"]
                    or settings["fixture"] != IDENTITIES):
                raise ValueError(f"Configuration fingerprint mismatch for {provider} {arm}")
        for index, (pair, order) in enumerate(zip(pairs, expected_order), start=1):
            identity = f"{provider}-{index:02d}"
            expected_runs = [{"arm": arm, "context_id": f"{identity}-{arm}",
                              "configuration_sha256": route["configurations"][arm]["sha256"]} for arm in order]
            if pair != {"pair_id": identity, "run_order": expected_runs}:
                raise ValueError(f"Order, fingerprint or fresh context mismatch for {identity}")
    counts = plan["session_counts"]
    if (counts["all_three_routes_if_qualified"] != sum(route["model_sessions"] for route in routes.values())
            or counts["historically_matched_routes_if_qualified"] !=
            sum(route["model_sessions"] for route in routes.values() if route["stage_1_2_pair_eligible"])
            or counts["authorized_now"] != 0):
        raise ValueError("Invalid session totals")


def make_plan(seed=DEFAULT_SEED):
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Seed must be an unsigned 64-bit integer")
    selected = report()["providers"]
    routes = {}
    for provider in ROUTES:
        archived = selected[provider]
        configurations = {}
        for arm, tool in TOOLS.items():
            settings = {
                "provider": provider, "arm": arm, "tool": tool, "fresh_context": True,
                "prompt_sha256": IDENTITIES[f"{arm}-prompt.txt"], "fixture": IDENTITIES,
                "client_model_and_isolation": archived[arm]["configuration"],
                "transport_qualification": "required",
            }
            configurations[arm] = {"sha256": digest(compact(settings, sort=True)), "settings": settings}
        pairs = []
        for index, order in enumerate(order_for(seed, provider), start=1):
            identity = f"{provider}-{index:02d}"
            pairs.append({"pair_id": identity, "run_order": [
                {"arm": arm, "context_id": f"{identity}-{arm}", "configuration_sha256": configurations[arm]["sha256"]}
                for arm in order]})
        routes[provider] = {
            "stage_1_2_pair_eligible": archived["pair_eligible"], "ready_for_live_resource_comparison": False,
            "open_gates": ["future_live_authorization", "native_or_independent_transport_qualification"] + (
                ["out_of_scope_control_requalification"] if provider == "grok" else []),
            "paired_runs": PAIR_COUNT, "model_sessions": 2 * PAIR_COUNT,
            "configurations": configurations, "pairs": pairs,
        }
    plan = {
        "schema": "wpai.benchmark.repeatability-plan.v1", "execution_mode": "plan-only",
        "live_inference_authorized": False, "seed": seed,
        "order_algorithm": "SHA-256 ranks pair positions per route and chooses whether two or three start with control.",
        "context_policy": "Start each arm in a fresh independent context. Record cache counters; do not reset provider state.",
        "authorization_gate": AUTHORIZATION_GATE,
        "session_counts": {"authorized_now": 0, "historically_matched_routes_if_qualified": 20,
                           "all_three_routes_if_qualified": 30, "includes_qualification_sessions": False},
        "measurements": MEASUREMENTS, "routes": routes,
    }
    validate(plan)
    return plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", help="Print the plan (the default and only mode)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)
    print(json.dumps(make_plan(args.seed), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

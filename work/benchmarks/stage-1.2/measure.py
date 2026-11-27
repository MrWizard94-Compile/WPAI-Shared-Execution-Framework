"""Reconcile normalized trial evidence with the frozen synthetic oracle."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from benchmark import BENCH, exact, parse, prompt


PROVIDERS = ("codex", "grok", "antigravity")
CLOCK = "2034-06-18T12:00:00.000Z"


def compact(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def expected_replies(arm, facts):
    if arm == "control":
        return [{"contract": "wpai.benchmark.field.v1", "status": "OK", "field": key, "fact": fact}
                for key, fact in facts.items()]
    return [{"contract": "wpai.repo_health.v1", "status": "OK", "project": "fictional-clockwork-museum",
             "opened_at": CLOCK, "closed_at": CLOCK, "facts": facts,
             "measurements": {"elapsed_ms": 0, "git_process_attempts": 0, "github_get_process_attempts": 0,
                              "provider_usage": "unavailable"}}]


def reconcile(record, oracle):
    trace = record["server_trace"]
    arm = record["arm"]
    calls = [row for row in trace if row["event"] == "acquisition"]
    replies = [row for row in trace if row["event"] == "sent" and row["method"] == "tools/call"]
    successes = [row for row in replies if row.get("ok")]
    client_starts = [row for row in record.get("client_tool_starts", []) if row.get("is_fixture")]
    client_completed = [row for row in record.get("client_tool_results", []) if row.get("is_fixture") and row.get("status") == "completed"]
    client_results = [row for row in client_completed if row.get("has_result")]
    keys = [row["field"] for row in calls if row.get("status") == "OK" and row.get("field")]
    expected = expected_replies(arm, oracle["facts"])
    expected_hashes = [sha256(compact(value).encode()).hexdigest() for value in expected]
    answer = record.get("validated_answer")
    complete_data = ([row["report_sha256"] for row in successes] == expected_hashes
                     and all(row.get("parity") for row in successes))
    exact_answer = exact(answer, oracle)
    elapsed = record["run_elapsed_seconds"]
    usage = record.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    provider = record["provider"]
    if provider == "codex":
        input_tokens = usage.get("input_tokens")
        cached = usage.get("cached_input_tokens")
        cache_creation = usage.get("cache_write_input_tokens")
        output = usage.get("output_tokens")
        reasoning = usage.get("reasoning_output_tokens")
        total = None if input_tokens is None or output is None else input_tokens + output
        definition = "input includes cached input; total equals input plus output and is derived"
    elif provider == "grok":
        source = (usage.get("input_tokens"), usage.get("cache_read_input_tokens"), usage.get("cache_creation_input_tokens"))
        input_tokens = sum(source) if all(isinstance(n, int) for n in source) else None
        cached = source[1]
        cache_creation = source[2]
        output = usage.get("output_tokens")
        reasoning = usage.get("reasoning_tokens")
        total = usage.get("total_tokens")
        definition = "Grok reports uncached input separately; input shown sums uncached, cache read and cache creation"
    else:
        input_tokens = None
        cached = usage.get("cachedReadTokens")
        cache_creation = usage.get("cachedWriteTokens")
        output = usage.get("outputTokens")
        reasoning = usage.get("thoughtTokens")
        total = usage.get("totalTokens")
        definition = "Antigravity ACP reported totals; cached subsets and thought tokens are left as reported"
    server_stop = next((row for row in reversed(trace) if row["event"] == "stop"), None)
    result = {
        "model": record.get("model"), "model_identity_source": record.get("model_identity_source", "unavailable"),
        "reasoning": record.get("reasoning_setting"), "protocol": record["server_protocols"],
        "client_observed_benchmark_calls": len(client_starts), "client_observed_tool_results": len(client_results),
        "client_observed_completed_tools": len(client_completed),
        "server_successes": len(successes), "server_failures": len(replies) - len(successes),
        "tool_call_rounds": "unavailable", "model_calls": record.get("model_calls", "unavailable"),
        "agent_turns": record.get("agent_turns", "unavailable"), "ordered_control_fields": keys,
        "independent_delivered_payloads_match": complete_data,
        "confirmed_model_tool_invocation": bool(client_starts and calls),
        "same_oracle_answer": exact_answer, "fields_exact": record.get("answer_score", {}).get("exact_fields", 0),
        "input_tokens_including_known_cache": input_tokens,
        "raw_input_tokens": usage.get("inputTokens", usage.get("input_tokens")), "cached_input_tokens": cached,
        "cache_creation_tokens": cache_creation, "output_tokens": output, "reasoning_tokens": reasoning,
        "total_tokens": total, "token_definition": definition,
        "provider_reported_cost_usd": record.get("provider_reported_cost_usd", "unavailable"),
        "whole_run_seconds_including_preflight": elapsed,
        "provider_phase_seconds": record.get("prompt_elapsed_seconds", "unavailable"),
        "server_metrics": record["server_metrics"], "clean_server_exit_observed": bool(server_stop and server_stop.get("code") == 0),
        "server_exit_code": server_stop.get("code") if server_stop else "unavailable",
        "maximum_memory": "unavailable", "server_pids_verified_gone": bool(record["server_processes"]) and all(
            state == "gone" for state in record["server_processes"]),
    }
    result["measurable_success"] = (complete_data and exact_answer and len(client_starts) == len(expected)
                                    and len(client_completed) == len(expected) and not record.get("out_of_scope_tool_events")
                                    and bool(record["server_protocols"]))
    return {key: value if value is not None else "unavailable" for key, value in result.items()}


def compare(directory):
    oracle = parse((BENCH / "ground_truth.json").read_bytes())
    pairs = {}
    for provider in PROVIDERS:
        raws = [parse((directory / f"{provider}-{arm}.json").read_bytes()) for arm in ("control", "treatment")]
        for record in raws:
            assert record["prompt_sha256"] == sha256(prompt(record["arm"]).encode()).hexdigest()
            assert record["temporary_directory_removed"] and all(state == "gone" for state in record["server_processes"])
            assert record["server_metrics"]["process_attempts"] == 0
        control, treatment = [reconcile(record, oracle) for record in raws]
        comparable = (control["measurable_success"] and treatment["measurable_success"]
                      and all(control[key] == treatment[key] for key in ("model", "protocol", "reasoning")))
        reductions = {}
        if comparable:
            for key in ("client_observed_benchmark_calls", "model_calls", "whole_run_seconds_including_preflight",
                        "input_tokens_including_known_cache", "total_tokens", "provider_reported_cost_usd"):
                a, b = control[key], treatment[key]
                if isinstance(a, (int, float)) and isinstance(b, (int, float)) and a > 0:
                    reductions[key] = round((a - b) / a, 6)
        pairs[provider] = {"matched_and_accurate": comparable, "control": control, "treatment": treatment,
                           "observed_reduction_fractions": reductions}
    return pairs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.results), indent=2))

"""Reconcile selected Stage 1.2 trials and retained attempts from raw records."""

import argparse
import json

from evidence import (ARCHIVE, IDENTITIES, PROTOCOLS, ROUTES, SOURCE, TOOLS, compact, digest, is_run_id,
                      number, obj, parse, read, rows, text_value, verify_inputs)


CLOCK = "2034-06-18T12:00:00.000Z"
HISTORICAL_METRICS = ("client_observed_benchmark_calls", "model_calls", "whole_run_seconds_including_preflight",
                      "input_tokens_including_known_cache", "total_tokens", "provider_reported_cost_usd")
RESOURCE_METRICS = (*HISTORICAL_METRICS[1:], "agent_turns", "provider_phase_seconds", "raw_input_tokens",
                    "cached_input_tokens", "cache_creation_tokens", "output_tokens", "reasoning_tokens",
                    "server_report_json_bytes", "server_rpc_wire_bytes", "server_acquisition_ms",
                    "server_call_round_trip_ms", "server_serialization_ms")
TOOL_METRICS = (HISTORICAL_METRICS[0], "server_operation_count")
METRIC_DEFINITIONS = {
    "codex": "Input includes cache reads. Total is derived from recorded input plus output.",
    "antigravity": "ACP total is reported directly. The normalized input partition is unavailable.",
    "grok": "Input is uncached input plus cache read and cache creation. Total and USD are CLI telemetry.",
}
ROUTE_ISOLATION = {
    "codex": {"shell_disabled": True, "apps_hooks_memory_subagents_web_disabled": True,
              "credentials_source_referenced_not_copied": True},
    "antigravity": {"terminal_sandbox": True, "customizations_disabled": True, "host_methods_denied": True},
    "grok": {"permissions": "exact allow with dontAsk", "no_hooks_or_enabled_plugins": True,
             "credentials_source_referenced_not_copied": True},
}


def expected_replies(arm, facts):
    if arm == "control":
        return [{"contract": "wpai.benchmark.field.v1", "status": "OK", "field": key, "fact": fact}
                for key, fact in facts.items()]
    return [{"contract": "wpai.repo_health.v1", "status": "OK", "project": "fictional-clockwork-museum",
             "opened_at": CLOCK, "closed_at": CLOCK, "facts": facts,
             "measurements": {"elapsed_ms": 0, "git_process_attempts": 0, "github_get_process_attempts": 0,
                              "provider_usage": "unavailable"}}]


def equal_json(left, right):
    try:
        return compact(left, sort=True) == compact(right, sort=True)
    except (TypeError, ValueError, RecursionError):
        return False


def trace_outcomes(record, facts):
    provider, arm = record["provider"], record["arm"]
    trace = rows(record.get("server_trace"))
    calls = [row for row in trace if row.get("event") == "acquisition"]
    sent = [row for row in trace if row.get("event") == "sent"]
    replies = [row for row in sent if row.get("method") == "tools/call"]
    success = [row for row in replies if row.get("ok") is True]
    received = [row.get("method") for row in trace if row.get("event") == "received"]
    starts = [row for row in trace if row.get("event") == "start"]
    stops = [row for row in trace if row.get("event") == "stop"]
    expected = [compact(reply) for reply in expected_replies(arm, facts)]
    order = list(facts) if arm == "control" else [None]
    protocol = PROTOCOLS[provider]
    methods = ["server/discover" if provider == "antigravity" else "initialize", "tools/list"] + [
        "tools/call"] * len(expected)
    digests_valid = len(replies) == len(expected) and all(
        reply.get("ok") is True and reply.get("report_sha256") == digest(payload)
        and reply.get("parity") is True and type(reply.get("report_json_bytes")) is int
        and reply["report_json_bytes"] == len(payload)
        for reply, payload in zip(replies, expected))
    operations_valid = (len(calls) == len(order)
                        and all(row.get("tool") == TOOLS[arm] and "field" in row and row["field"] == field
                                and row.get("status") == "OK"
                                and number(row.get("process_attempts"), integer=True) == 0
                                for row, field in zip(calls, order)))
    methods_valid = (received == methods and [row.get("method") for row in sent] == methods
                     and all(row.get("ok") is True and row.get("protocol") == protocol for row in sent))
    events = [row.get("event") for row in trace if row.get("event") != "serialization"]
    event_order = ["start", "received", "sent", "received", "sent"] + [
        "received", "acquisition", "sent"] * len(expected)
    trace_order_valid = events == event_order or events == [*event_order, "stop"]
    protocol_valid = record.get("server_protocols") == [protocol] and methods_valid

    def trace_sum(items, field, *, integer=False):
        values = [number(row.get(field), integer=integer) for row in items]
        if values and all(value is not None for value in values):
            return sum(values) if integer else round(sum(values), 4)
        return None

    return {
        "expected_server_operations": len(expected), "server_operation_count": len(calls) if trace else None,
        "server_tool_requests": received.count("tools/call") if trace else None,
        "successful_server_operations": len(success) if trace else None,
        "failed_or_unanswered_server_operations": (max(len(calls), len(replies), received.count("tools/call"))
                                                   - len(success)) if trace else None,
        "ordered_control_fields": [row.get("field") for row in calls] if arm == "control" else None,
        "successful_reply_digests": [row.get("report_sha256") for row in success],
        "exact_reply_digests_valid": digests_valid, "expected_server_execution_observed": (
            digests_valid and operations_valid and methods_valid and trace_order_valid and protocol_valid
            and len(starts) == 1 and starts[0].get("arm") == arm),
        "observed_protocols": record.get("server_protocols"), "protocol_identity_valid": protocol_valid,
        "server_report_json_bytes": trace_sum(replies, "report_json_bytes", integer=True),
        "server_rpc_wire_bytes": trace_sum(replies, "wire_bytes", integer=True),
        "server_acquisition_ms": trace_sum(calls, "acquisition_ms"),
        "server_call_round_trip_ms": trace_sum(replies, "round_trip_ms"),
        "server_serialization_ms": trace_sum([row for row in trace if row.get("event") == "serialization"],
                                             "serialization_ms"),
        "server_process_attempts": trace_sum(calls, "process_attempts", integer=True),
        "archived_server_stop": stops[0] if len(stops) == 1 else None,
        "server_stop_events": len(stops),
    }


def lifecycle_outcomes(record, server):
    proof = obj(record.get("lifecycle"))
    stop = server["archived_server_stop"]
    app_code = number(stop.get("code"), integer=True) if stop else None
    if proof.get("schema") == "wpai.benchmark.lifecycle.v1":
        code = number(proof.get("server_exit_code"), integer=True)
        eof = proof.get("server_eof_observed")
        forced = proof.get("forced_termination")
        active = number(proof.get("active_processes_at_check"), integer=True)
        owned = number(proof.get("processes_in_owned_job"), integer=True)
        gone = proof.get("process_tree_verified_gone") is True and active == 0 and owned is not None and owned > 0
        valid = (is_run_id(record.get("run_id")) and proof.get("run_id") == record["run_id"]
                 and proof.get("arm") == record["arm"] and equal_json(proof.get("fixture_identities"), IDENTITIES)
                 and proof.get("client_stdin_eof") is True and proof.get("child_stdin_closed") is True
                 and eof is True and code == 0 and forced is False and gone
                 and proof.get("transport_ok") is True and proof.get("transport_faults") == []
                 and proof.get("termination_reason") == "child_exited")
    else:
        code = eof = forced = gone = None
        valid = False
    client = obj(record.get("client_process"))
    archived_failed = (server["server_stop_events"] > 1 or
                       (stop is not None and (app_code != 0 or stop.get("worker_alive") is not False)))
    client_valid = number(client.get("exit_code"), integer=True) == 0 and client.get("forced") is False
    valid = valid and not archived_failed and client_valid
    known_failure = archived_failed or (bool(client) and not client_valid) or ("lifecycle" in record and not valid)
    roots = record.get("server_processes")
    return {
        "server_eof_observed": eof if type(eof) is bool else None,
        "server_exit_code": code, "forced_termination": forced if type(forced) is bool else None,
        "process_tree_verified_gone": gone, "lifecycle_valid": valid,
        "lifecycle_status": "pass" if valid else "fail" if known_failure else "open",
        "client_exit_zero_unforced": client_valid,
        "archived_server_application_exit_code": app_code,
        "archived_fixture_roots_seen_gone": isinstance(roots, list) and bool(roots) and all(state == "gone" for state in roots),
    }


def execution_conditions(record):
    provider, arm = record["provider"], record["arm"]
    isolation = obj(record.get("isolation"))
    stable = {key: val for key, val in isolation.items() if key not in ("only_mcp_tool", "permission_decisions")}
    configuration = {key: text_value(record.get(key)) for key in (
        "model", "model_identity_source", "client_version", "auth_category", "reasoning_setting",
        "requested_model", "client_routing_hint_sha256")}
    configuration.update(isolation=stable, protocol=PROTOCOLS[provider],
                         acp_version=number(record.get("acp_version"), integer=True))
    required = ("model", "model_identity_source", "client_version", "auth_category")
    known = all(configuration[key] is not None for key in required)
    settings_known = (equal_json(stable, {"only_mcp_server": "wpai_benchmark", **ROUTE_ISOLATION[provider]})
                      and isolation.get("only_mcp_tool") == TOOLS[arm])
    if provider == "antigravity":
        decisions = rows(isolation.get("permission_decisions"))
        settings_known = (settings_known and configuration["acp_version"] is not None
                          and record.get("normal_settings_unchanged") is True
                          and record.get("isolated_app_data_removed") is True
                          and len(decisions) == (12 if arm == "control" else 1)
                          and all(row.get("fixture_match") is True and row.get("allow_once_available") is True
                                  and row.get("decision") == "allow_once" and row.get("server_label_present") is True
                                  for row in decisions))
    else:
        settings_known = (settings_known and configuration["reasoning_setting"] is not None
                          and configuration["requested_model"] is not None
                          and record.get("normal_auth_file_unchanged") is True)
        if provider == "grok":
            settings_known = settings_known and configuration["client_routing_hint_sha256"] is not None
    return configuration, known, settings_known


def usage_metrics(record):
    provider = record["provider"]
    raw = obj(record.get("usage"))

    def tokens(name):
        return number(raw.get(name), integer=True)

    if provider == "codex":
        source, cached, created = map(tokens, ("input_tokens", "cached_input_tokens", "cache_write_input_tokens"))
        output, reasoning = map(tokens, ("output_tokens", "reasoning_output_tokens"))
        normalized = source
        total = source + output if source is not None and output is not None else None
    elif provider == "grok":
        source, cached, created = map(tokens, ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        output, reasoning, total = map(tokens, ("output_tokens", "reasoning_tokens", "total_tokens"))
        normalized = sum((source, cached, created)) if None not in (source, cached, created) else None
    else:
        source, cached, created = map(tokens, ("inputTokens", "cachedReadTokens", "cachedWriteTokens"))
        output, reasoning, total = map(tokens, ("outputTokens", "thoughtTokens", "totalTokens"))
        normalized = None
    return {
        "raw_input_tokens": source, "cached_input_tokens": cached, "cache_creation_tokens": created,
        "output_tokens": output, "reasoning_tokens": reasoning, "total_tokens": total,
        "input_tokens_including_known_cache": normalized,
        "agent_turns": number(record.get("agent_turns"), integer=True),
        "model_calls": number(record.get("model_calls"), integer=True),
        "provider_reported_cost_usd": number(record.get("provider_reported_cost_usd")) if provider == "grok" else None,
        "actual_billable_api_charge_usd": number(record.get("actual_billable_api_charge")),
        "subscription_quota_delta": None, "model_only_latency_seconds": None, "tool_call_rounds": None,
        "whole_run_seconds_including_preflight": number(record.get("run_elapsed_seconds")),
        "provider_phase_seconds": number(record.get("prompt_elapsed_seconds")),
    }


def reconcile(record, oracle, *, archived=False):
    provider, arm = record["provider"], record["arm"]
    facts = oracle["facts"]
    answer = record.get("validated_answer")
    actual_facts = obj(obj(answer).get("facts"))
    exact_fields = sum(key in actual_facts and equal_json(actual_facts[key], value) for key, value in facts.items())
    final = record.get("final_response_received") is True
    answer_valid = final and equal_json(answer, oracle)
    server = trace_outcomes(record, facts)
    lifecycle = lifecycle_outcomes(record, server)
    configuration, identity_known, settings_known = execution_conditions(record)
    starts, results = (record.get(key) for key in ("client_tool_starts", "client_tool_results"))
    fixture_starts = [row for row in rows(starts) if row.get("is_fixture") is True
                      and row.get("status") == {"antigravity": "completed", "codex": "in_progress", "grok": None}[provider]]
    completed = [row for row in rows(results) if row.get("is_fixture") is True and row.get("status") == "completed"]
    n = server["expected_server_operations"]
    starts_valid = len(fixture_starts) == n and len(starts) == n
    completions_valid = len(completed) == n and len(results) == n
    extra = record.get("out_of_scope_tool_events")
    out_of_scope = extra if isinstance(extra, list) else None
    expected_calls = starts_valid and completions_valid and server["expected_server_execution_observed"]
    observed_tally = len(fixture_starts) if isinstance(starts, list) else None
    independently_measured_bytes = record.get("client_observed_result_bytes")
    result_bytes = number(independently_measured_bytes, integer=True)
    if not completions_valid or not all(row.get("has_result") is True for row in completed):
        result_bytes = None
    metrics = {"client_observed_benchmark_calls": observed_tally, **usage_metrics(record)}
    metrics.update({key: server[key] for key in (*TOOL_METRICS[1:], *RESOURCE_METRICS) if key in server})
    tool_valid = expected_calls and out_of_scope == [] and lifecycle["lifecycle_status"] != "fail"
    prompt_matches = record.get("prompt_sha256") == IDENTITIES[f"{arm}-prompt.txt"]
    packet_identified = equal_json(record.get("fixture_identities"), IDENTITIES)
    pair_eligible = (record.get("model_prompt_started") is True and identity_known and settings_known
                     and prompt_matches and answer_valid and tool_valid and lifecycle["client_exit_zero_unforced"]
                     and record.get("temporary_directory_removed") is True and not record.get("blocked")
                     and record.get("stop_reason") in (None, "end_turn")
                     and (lifecycle["archived_fixture_roots_seen_gone"] if archived else
                          lifecycle["lifecycle_valid"] and packet_identified))
    return {
        "model_session_started": record.get("model_prompt_started") if type(record.get("model_prompt_started")) is bool else None,
        "model_identity_observed": identity_known, "execution_settings_observed": settings_known,
        "configuration": configuration, "prompt_sha256_valid": prompt_matches, "run_fixture_identities_valid": packet_identified,
        "client_fixture_start_count": observed_tally, "expected_client_tool_starts_observed": starts_valid,
        "client_fixture_completion_count": len(completed) if isinstance(results, list) else None,
        "expected_client_tool_completions_observed": completions_valid,
        "client_tool_result_events_with_result": (sum(row.get("has_result") is True for row in completed)
                                                  if isinstance(results, list) else None),
        "client_observed_result_bytes_available": result_bytes is not None, "client_observed_result_bytes": result_bytes,
        "out_of_scope_tool_activity": out_of_scope, "expected_tool_execution_observed": expected_calls,
        "tool_execution_valid": tool_valid, **server, **lifecycle,
        "final_response_received": final, "exact_fields": exact_fields, "answer_valid": answer_valid,
        "pair_eligible": pair_eligible, "resource_metrics_eligible": (
            pair_eligible and lifecycle["lifecycle_valid"] and packet_identified
            and any(metrics[key] is not None for key in RESOURCE_METRICS)),
        "usage_telemetry_available": any(metrics[key] is not None for key in (
            "raw_input_tokens", "cached_input_tokens", "cache_creation_tokens", "output_tokens",
            "reasoning_tokens", "total_tokens", "model_calls")),
        "cost_telemetry_available": metrics["provider_reported_cost_usd"] is not None,
        "usage_definition": METRIC_DEFINITIONS[provider], "metrics": metrics,
    }


def compare_pair(control, treatment, oracle, *, archived=False):
    if (control.get("provider") != treatment.get("provider") or control.get("arm") != "control"
            or treatment.get("arm") != "treatment"):
        raise ValueError("Expected ordered control and treatment from one provider")
    left, right = (reconcile(record, oracle, archived=archived) for record in (control, treatment))
    matched = equal_json(left["configuration"], right["configuration"])
    eligible = (matched and left["pair_eligible"] and right["pair_eligible"]
                and (archived or control.get("run_id") != treatment.get("run_id")))
    strict = eligible and left["resource_metrics_eligible"] and right["resource_metrics_eligible"]
    available = {key: eligible and left["metrics"][key] is not None and right["metrics"][key] is not None
                 for key in (*TOOL_METRICS, *RESOURCE_METRICS)}
    # Provider, client build, identities, and metric definitions are matched before calculating.
    gates = {key: both and (key in TOOL_METRICS or strict) for key, both in available.items()}

    def reductions(gate):
        return {key: round((left["metrics"][key] - right["metrics"][key]) / left["metrics"][key], 6)
                for key, passes in gate.items() if passes and left["metrics"][key] > 0}

    result = {
        "control": left, "treatment": right, "matching_execution_conditions": matched, "pair_eligible": eligible,
        "resource_metrics_eligible": any(gates[key] for key in RESOURCE_METRICS),
        "metric_eligibility": gates,
        "eligible_reduction_fractions": reductions(gates),
    }
    if archived:
        result["historical_observed_reduction_fractions"] = reductions({key: available[key] for key in HISTORICAL_METRICS})
    return result


def report():
    verify_inputs()
    oracle = read(SOURCE / "ground_truth.json")
    historical = read(ARCHIVE / "comparison.json")
    sources = {}

    def load(path):
        data = path.read_bytes()
        sources[path.relative_to(ARCHIVE).as_posix()] = digest(data)
        return parse(data)

    pairs = {}
    for provider in ROUTES:
        pair = compare_pair(*(load(ARCHIVE / "runs" / f"{provider}-{arm}.json") for arm in TOOLS), oracle, archived=True)
        old = historical[provider]
        if (pair["historical_observed_reduction_fractions"] != old["observed_reduction_fractions"]
                or pair["pair_eligible"] != old["matched_and_accurate"]):
            raise ValueError(f"Archived reduction or disposition differs for {provider}")
        pairs[provider] = pair
    attempts = {}
    for path in sorted((ARCHIVE / "attempts").glob("*.json")):
        record = load(path)
        decisions = rows(obj(record.get("isolation")).get("permission_decisions"))
        attempts[path.name] = {
            "disposition": "discarded", "provider": record["provider"], "arm": record["arm"],
            "blocked_reason": record.get("blocked"), "client_stop_reason": record.get("stop_reason"),
            "permission_decisions": [row.get("decision") for row in decisions],
            "permission_fixture_matches": sum(row.get("fixture_match") is True for row in decisions),
            **reconcile(record, oracle, archived=True),
        }
    return {
        "schema": "wpai.benchmark.reconciliation.v1", "frozen_identities": IDENTITIES, "source_record_sha256": sources,
        "historical_lifecycle_notes": {
            "codex": "Root gone. No server stop or EOF observation or OS exit code in the selected records.",
            "grok": "Root gone. No server stop or EOF observation or OS exit code in the selected records.",
            "antigravity": ("Stage 1.2 reported clean EOF and exit 0 for both arms. The raw stop events confirm application "
                            "return 0 and worker stopped. The archived event has no EOF reason, independent OS exit "
                            "code or process-tree verification. The Stage 1.3 lifecycle gate remains open."),
        },
        "providers": pairs, "discarded_attempts": attempts,
    }


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(report(), indent=2, allow_nan=False))

"""Build and enforce the Stage 1.7 public static account-isolation matrix."""

from collections import Counter
from graphlib import CycleError, TopologicalSorter
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from catalog import (APPLICABILITY, BASE, CATALOG, CODEX_SHA, CONSTITUTION, CURRENT, DECISIONS, EXACT, EXACT_DOC,
                     GROK_BUILD, HISTORICAL_ROUTES, HISTORY, LABELS, PREFERENCE_EDGES, TOPICS, UNKNOWN, VERSIONS)


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
OUTPUT = ROOT / "outputs" / "stage-1.7"
SCHEMA = "wpai.benchmark.provider-account-isolation.v1"
PLAN = "outputs/stage-1.3/repeatability-plan.json"
PLAN_SHA = "2655c6732c919abdd7624d36cd12296234f20443e09b78f5f354e5bf29003224"
PRIOR_SHA = "7be11e1c7aafcf3e89e1069e2598639fbacb6b3ffbb66db8c4a1607c1c5176a4"
SOURCE_PREFIX = f"https://github.com/openai/codex/blob/{CODEX_SHA}/codex-rs/"
RELEASE = "https://github.com/openai/codex/releases/tag/rust-v0.166.0"
EXACT_LABELS = {EXACT, EXACT_DOC}
AUTH = {"authorized_now": 0, "provider_processes_started": 0, "live_provider_sessions": 0,
        "provider_api_calls": 0, "account_or_config_changes": 0, "paired_study_authorized": False,
        "native_qualification_started": False}
SESSION_COUNTS = {"authorized_now": 0, "historically_matched_routes_if_qualified": 20,
                  "all_three_routes_if_qualified": 30, "includes_qualification_sessions": False}
DOC_OWNERS = {"codex": {"learn.chatgpt.com", "developers.openai.com"},
              "antigravity": {"antigravity.google"}, "grok": {"docs.x.ai"}}
PREFIXES = {"codex": "cx-", "antigravity": "ag-", "grok": "gr-"}
UNKNOWN_PRECEDENCE = {
    "codex": ["Effective host policy and tool catalog", "Thread-specific ordering and any separate plugin or update state"],
    "antigravity": ["Exact Windows policy and scope merge order", "Independently loaded authentication and worker state"],
    "grok": ["Exact Windows policy, workspace, imports, environment and CLI merge", "Background and updater state outside the home"],
}
CURRENT_ORDER_CONTEXT = {
    "codex": [],
    "antigravity": ["ag-settings-doc", "ag-shared-doc"],
    "grok": ["gr-config-doc", "gr-policy-doc", "gr-mcp-doc"],
}

# Reuse the strict, narrow JSON Schema evaluator already exercised in Stage 1.5.
sys.path.insert(0, str(SOURCE.parent / "stage-1.5"))
try:
    from route_matrix import validate_schema
finally:
    sys.path.pop(0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    value = {}
    for key, member in pairs:
        require(key not in value, "Duplicate JSON field")
        value[key] = member
    return value


def invalid_number(_):
    raise ValueError("Nonfinite JSON constant")


def decode(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_number)


def frozen_file(relative, digest):
    data = (ROOT / relative).read_bytes()
    require(sha256(data).hexdigest() == digest, f"Frozen input changed: {relative}")
    return decode(data)


def frozen_inputs():
    plan = frozen_file(PLAN, PLAN_SHA)
    prior = frozen_file(HISTORICAL_ROUTES, PRIOR_SHA)
    pairs = {name: row["paired_runs"] for name, row in plan["routes"].items()}
    require(plan["live_inference_authorized"] is False and plan["session_counts"] == SESSION_COUNTS
            and pairs == dict.fromkeys(VERSIONS, 5), "Repeatability authority or session limits changed")
    total = sum(trial["sessions"] for route in prior["routes"].values() for trial in route["trials"])
    require(prior["authorized_now"] == prior["live_provider_sessions_started"] == 0
            and prior["live_inference_authorized"] is False and total == prior["future_sessions_if_all_authorized"] == 6
            and all(not row["native_qualified"] and row["authorized_sessions"] == 0 for row in prior["routes"].values())
            and prior["frozen_repeatability"]["session_counts"] == SESSION_COUNTS, "Stage 1.5 snapshot lost its authorization boundary")
    return {"repeatability_sha256": PLAN_SHA, "stage_1_5_matrix_sha256": PRIOR_SHA, "proposed_lifecycle_cases": total,
            "session_counts": plan["session_counts"], "paired_runs": pairs}, prior["routes"]


def version_record(name, frozen_route):
    row = frozen_route["version"]
    require(row["stage_1_2"] == row["installed"] == VERSIONS[name], "Unexpected historical client version")
    return {
        "historical": row["stage_1_2"], "installed_record": row["installed"], "executable": row["executable"],
        "algorithm": row["digest_algorithm"], "digest": row["digest"], "artifact": row["artifact"],
        "matched_source": None if row["matched_source"] == UNKNOWN else row["matched_source"],
        "release_tag": "rust-v0.166.0" if name == "codex" else None,
        "build_marker": GROK_BUILD if name == "grok" else None,
    }


def counts(claims):
    totals = Counter(row["class"] for row in claims)
    return {label: totals[label] for label in LABELS}


def route(name, frozen_route):
    version = version_record(name, frozen_route)
    claims = [{**row, "provider": name, "version": version["historical"]} for row in CATALOG[name]()]
    matched = version["matched_source"] is not None
    decision = DECISIONS[name]
    gates = {key: {"status": status, "claims": list(refs)}
             for key, (status, refs) in decision["essential_gates"].items()}
    edges = [{"lower": low, "higher": high, "claim": ref} for low, high, ref in PREFERENCE_EDGES] if matched else []
    return {
        "product": frozen_route["product"], "version": version, "historical_mode": frozen_route["historical_mode"],
        "provenance": "matched_source" if matched else "unresolved_source", "decision": "NO-GO",
        "native_qualified": False, "authorized_sessions": 0, "future_preflight_eligible": False,
        "managed_policy_authoritative": True, "classification": decision["classification"],
        "blocked_by": decision["blocked_by"], "future": decision["future"], "essential_gates": gates,
        "precedence": {"status": "exact_partial" if matched else "unknown_exact", "exact_edges": edges,
                       "current_context": CURRENT_ORDER_CONTEXT[name], "unknowns": UNKNOWN_PRECEDENCE[name]},
        "claims": claims, "evidence_counts": counts(claims),
    }


def validate_claim(item, name, version):
    ident, label, source = item["id"], item["class"], item["source"]
    require(ident.startswith(PREFIXES[name]) and item["provider"] == name and item["version"] == version["historical"],
            f"{ident}: provider or target version mismatch")
    require(source["applicability"] == APPLICABILITY[label], f"{ident}: evidence applicability mismatch")
    topics = set(item["topics"])
    require(topics <= TOPICS and len(topics) == len(item["topics"]), f"{ident}: unknown or repeated topic")
    location, revision = source["location"], source["revision"]
    url = urlsplit(location)
    if url.scheme:
        require(url.scheme == "https" and bool(url.hostname) and not url.username
                and not url.password and not url.query, f"{ident}: source URL is not a public immutable reference or clean docs link")
    else:
        path = Path(location)
        require(path.as_posix() == location and not path.is_absolute() and ".." not in path.parts
                and location.startswith(("outputs/stage-1.", "work/benchmarks/stage-1."))
                and (ROOT / path).is_file(), f"{ident}: invalid archived path")
    if label == EXACT:
        require(name == "codex" and revision == version["matched_source"] == CODEX_SHA
                and location.startswith(SOURCE_PREFIX) and re.fullmatch(r"L\d+(?:-L\d+)?", url.fragment),
                f"{ident}: source is not matched to the pinned artifact")
    elif label == EXACT_DOC:
        require(name == "codex" and revision == version["release_tag"] and location.partition("#")[0] == RELEASE,
                f"{ident}: rolling or unmatched docs cannot supply exact behavior")
    elif label == CURRENT:
        require(revision is None and url.hostname in DOC_OWNERS[name], f"{ident}: unpinned official documentation required")
    elif label == HISTORY:
        require(revision == BASE and not url.scheme, f"{ident}: archive observation needs frozen repository provenance")
    elif label == UNKNOWN:
        require(revision is None, f"{ident}: missing evidence cannot carry a matched version")


def validate_precedence(name, row, claims):
    order = row["precedence"]
    edges = order["exact_edges"]
    graph = TopologicalSorter()
    seen = set()
    for edge in edges:
        low, high, reference = edge["lower"], edge["higher"], edge["claim"]
        require(reference in claims and claims[reference]["class"] in EXACT_LABELS
                and "configuration_precedence" in claims[reference]["topics"],
                f"{name}: precedence edge has no exact configuration evidence")
        require((low, high) not in seen and low != high and low != "enforced_requirements",
                f"{name}: precedence would repeat, self-reference or bypass managed requirements")
        seen.add((low, high))
        graph.add(high, low)
    try:
        tuple(graph.static_order())
    except CycleError as error:
        raise ValueError(f"{name}: configuration precedence cycle") from error
    expected = tuple((item["lower"], item["higher"], item["claim"]) for item in edges)
    require(expected == (PREFERENCE_EDGES if name == "codex" else ())
            and order["status"] == ("exact_partial" if name == "codex" else "unknown_exact"),
            f"{name}: published exact precedence must match the reviewed proof")
    require(all(ref in claims and claims[ref]["class"] == CURRENT for ref in order["current_context"]),
            f"{name}: rolling precedence needs separate current context")


def validate(data):
    schema = decode((SOURCE / "isolation-schema.json").read_bytes())
    validate_schema(data, schema, schema["$defs"])
    frozen, prior = frozen_inputs()
    require(data["baseline"] == BASE and data["constitution"] == CONSTITUTION and data["frozen"] == frozen
            and data["authorization"] == AUTH, "Baseline or authorization boundary differs")
    all_claims = []
    for name, row in data["routes"].items():
        version = version_record(name, prior[name])
        require(row["version"] == version and row["product"] == prior[name]["product"]
                and row["historical_mode"] == prior[name]["historical_mode"], f"{name}: pinned route identity differs")
        claims = {item["id"]: item for item in row["claims"]}
        require(len(claims) == len(row["claims"]), f"{name}: duplicate claim")
        for item in claims.values():
            validate_claim(item, name, version)
        require(set().union(*(set(item["topics"]) for item in claims.values())) == TOPICS,
                f"{name}: missing account or configuration topic")
        matched = version["matched_source"] is not None
        require(row["provenance"] == ("matched_source" if matched else "unresolved_source"),
                f"{name}: unresolved provenance was promoted")
        gates = row["essential_gates"]
        for gate_name, gate in gates.items():
            refs = gate["claims"]
            require(all(ref in claims for ref in refs) and len(set(refs)) == len(refs), f"{name}: invalid proof references")
            if gate["status"] in ("established", "contradicted"):
                require(any(claims[ref]["class"] in EXACT_LABELS for ref in refs),
                        f"{name}: {gate_name} lacks version-matched evidence")
            require((gate["status"], tuple(refs)) == DECISIONS[name]["essential_gates"][gate_name],
                    f"{name}: {gate_name} exceeds its reviewed evidence")
        require(gates["provenance"]["status"] == ("established" if matched else "unknown"),
                f"{name}: exact provenance missing")
        require(not all(gate["status"] == "established" for gate in gates.values())
                and row["classification"] == DECISIONS[name]["classification"],
                f"{name}: unsafe isolation verdict")
        validate_precedence(name, row, claims)
        require(row["evidence_counts"] == counts(row["claims"]), f"{name}: source classification counts differ")
        all_claims.extend(row["claims"])
    require(data["evidence_counts"] == counts(all_claims), "Aggregate source classification counts differ")


PRIVATE = re.compile(
    r"(?i)(?:[a-z]:[\\/]Users[\\/]|/(?:Users|home)/|\bBearer\s+[a-z0-9._~-]{16,}|"
    r"\b(?:sk-|xai-|gh[pousr]_|AIza)[a-z0-9_-]{24,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"""["']?(?:api[_-]?key|(?:access|refresh|id)[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["']?[^\s"'|]{12,})"""
)


def guard_public(text):
    require(PRIVATE.search(text) is None, "Possible secret or private path in public isolation evidence")


def render():
    frozen, prior = frozen_inputs()
    routes = {name: route(name, prior[name]) for name in VERSIONS}
    data = {"schema": SCHEMA, "baseline": BASE, "constitution": CONSTITUTION, "authorization": AUTH, "frozen": frozen,
            "evidence_counts": counts([claim for row in routes.values() for claim in row["claims"]]), "routes": routes}
    validate(data)
    result = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    guard_public(result)
    return result.encode("ascii")

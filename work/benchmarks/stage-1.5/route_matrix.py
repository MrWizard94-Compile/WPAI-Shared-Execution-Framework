"""Reproduce and validate the offline Stage 1.5 route feasibility matrix."""

from hashlib import sha256
import json
from pathlib import Path
import re

from route_catalog import BASELINE, CONSTITUTION, FROZEN_PLAN_SHA, UNKNOWN, routes


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
OUTPUT = ROOT / "outputs" / "stage-1.5"
SCHEMA_ID = "wpai.benchmark.native-route-feasibility.v1"
PROVIDERS = ("codex", "antigravity", "grok")
COUNTS = {"authorized_now": 0, "historically_matched_routes_if_qualified": 20,
          "all_three_routes_if_qualified": 30, "includes_qualification_sessions": False}
HISTORICAL_VERSIONS = {
    "codex": ("0.166.0", "codex-cli 0.166.0"),
    "antigravity": ("1.5.18", "1.5.18"),
    "grok": ("1.0.92", "grok 1.0.92 (b06756fd6256)"),
}


def frozen_repeatability():
    data = (ROOT / "outputs/stage-1.3/repeatability-plan.json").read_bytes()
    if sha256(data).hexdigest() != FROZEN_PLAN_SHA:
        raise ValueError("Frozen repeatability plan bytes changed")
    plan = json.loads(data)
    pairs = {name: record["paired_runs"] for name, record in plan["routes"].items()}
    require(plan["live_inference_authorized"] is False and plan["session_counts"] == COUNTS
            and pairs == dict.fromkeys(PROVIDERS, 5), "Frozen repeatability plan limits changed")
    return {"sha256": FROZEN_PLAN_SHA, "session_counts": plan["session_counts"], "paired_runs": pairs}


def require(condition, message):
    if not condition:
        raise ValueError(message)


SCHEMA_TYPES = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool, "null": type(None)}


def validate_schema(value, rule, definitions, path="$"):
    # Evaluate the subset of draft 2020-12 used by the committed schema.
    if "$ref" in rule:
        return validate_schema(value, definitions[rule["$ref"].removeprefix("#/$defs/")], definitions, path)
    kinds = rule.get("type", tuple(SCHEMA_TYPES))
    if isinstance(kinds, str):
        kinds = (kinds,)
    require(type(value) in tuple(SCHEMA_TYPES[key] for key in kinds), f"{path}: invalid type")
    if "const" in rule:
        require(type(value) is type(rule["const"]) and value == rule["const"], f"{path}: invalid constant")
    if "enum" in rule:
        require(value in rule["enum"], f"{path}: invalid option")
    if "pattern" in rule:
        require(re.fullmatch(rule["pattern"], value) is not None, f"{path}: invalid text")
    if isinstance(value, dict):
        properties = rule["properties"]
        require(set(rule["required"]) <= value.keys(), f"{path}: required field missing")
        require(rule.get("additionalProperties", True) or value.keys() <= properties.keys(),
                f"{path}: unexpected field")
        for key in value.keys() & properties.keys():
            validate_schema(value[key], properties[key], definitions, f"{path}.{key}")
    if isinstance(value, list):
        require(rule.get("minItems", 0) <= len(value) <= rule.get("maxItems", len(value)),
                f"{path}: invalid item count")
        for index, item in enumerate(value):
            validate_schema(item, rule["items"], definitions, f"{path}[{index}]")


PRIVATE_TEXT = re.compile(
    r"(?i)(?:[a-z]:[\\/]Users[\\/]|/(?:home|Users)/|"
    r"\bBearer\s+[a-z0-9._~-]{12,}|\b(?:sk-|gh[pousr]_|AIza)[a-z0-9_-]{16,}|"
    r"""["']?(?:api[_-]?key|(?:access|refresh|id)[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["']?[^\s"'|]{8,})"""
)
SESSION_COMMAND = re.compile(
    r"(?ix)\b(?:codex(?:\.exe)?[ \t]+(?:exec|app-server|resume)\b(?![ \t]+--help\b)|"
    r"agy(?:\.exe)?[ \t]+acp\b(?![ \t]+--help\b)|"
    r"grok(?:\.exe)?[ \t]+(?:agent\b(?![ \t]+--help\b)|-p\b|--(?:prompt|headless|yolo|always-approve)\b))"
)


def validate_public_text(data, *, plan=False):
    require(PRIVATE_TEXT.search(data) is None, "Possible credential value or private path in public evidence")
    if plan:
        require(SESSION_COMMAND.search(data) is None, "Executable provider session invocation in qualification plan")


def validate_matrix(data):
    schema = json.loads((SOURCE / "route-schema.json").read_bytes())
    validate_schema(data, schema, schema["$defs"])
    require(data["baseline"] == BASELINE and data["constitution"] == CONSTITUTION, "Baseline mismatch")
    require(data["frozen_repeatability"] == frozen_repeatability(), "Frozen session counts differ")
    reference = routes()
    for name, route in data["routes"].items():
        layers = {layer["id"]: layer for layer in route["layers"]}
        require(len(layers) == len(route["layers"]), f"{name}: duplicate process layer")
        by_kind = {layer["kind"]: layer for layer in layers.values()}
        require(set(("observer", "external_owner", "provider_client", "mcp_launcher", "synthetic_mcp_server"))
                <= by_kind.keys(), f"{name}: required distinct roles missing")
        require(by_kind["external_owner"]["parent"] == by_kind["observer"]["id"]
                and by_kind["synthetic_mcp_server"]["parent"] == by_kind["mcp_launcher"]["id"],
                f"{name}: required ownership edges missing")
        for layer in layers.values():
            seen = {layer["id"]}
            parent = layer["parent"]
            while parent not in (None, UNKNOWN):
                require(parent in layers and parent not in seen, f"{name}: invalid or cyclic process hierarchy")
                seen.add(parent)
                parent = layers[parent]["parent"]
        require([item["id"] for item in route["trials"]] == ["normal", "external_termination"],
                f"{name}: require distinct normal and forced trials")
        number, archived_version = HISTORICAL_VERSIONS[name]
        for arm in ("control", "treatment"):
            run = json.loads((ROOT / f"outputs/stage-1.2/runs/{name}-{arm}.json").read_bytes())
            require(run["client_version"] == archived_version, f"{name}: archived client version differs")
        require(route["version"]["stage_1_2"] == number == route["version"]["installed"]
                and all(item["client_version"] == number for item in route["trials"]),
                f"{name}: client version differs")
        require(route == reference[name], f"{name}: route diverges from the frozen evidence catalog")


def render():
    route_data = routes()
    data = {
        "schema": SCHEMA_ID, "baseline": BASELINE, "constitution": CONSTITUTION,
        "authorized_now": 0, "live_provider_sessions_started": 0, "live_inference_authorized": False,
        "native_provider_qualification_started": False,
        "future_sessions_if_all_authorized": sum(item["sessions"] for route in route_data.values()
                                                for item in route["trials"]),
        "frozen_repeatability": frozen_repeatability(), "routes": route_data,
    }
    validate_matrix(data)
    result = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    validate_public_text(result)
    return result.encode("utf-8")

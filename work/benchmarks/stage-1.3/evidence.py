"""Frozen Stage 1.2 inputs and strict JSON evidence utilities."""

from hashlib import sha256
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "work" / "benchmarks" / "stage-1.2"
ARCHIVE = ROOT / "outputs" / "stage-1.2"
ROUTES = ("codex", "antigravity", "grok")
TOOLS = {"control": "fixture_read_field_v1", "treatment": "repo_health_v1"}
PROTOCOLS = {"codex": "2025-06-18", "antigravity": "2026-07-28", "grok": "2025-11-25"}
IDENTITIES = {
    "stage_1_1_package": "9063cd629145fee025a6330dd969a6bb608bc2571cca72dde5860947652a3686",
    "ground_truth.json": "1eb47cd4ebc554a490b3cc439440f927fced1cc052aa3d634cdd2e97941092f8",
    "response_schema.json": "66760159677ef20e42b112a317b2fff28947c9994bb347b6361dcc4a9568448e",
    "control-prompt.txt": "df1ebe1690b16b813970a5c42f60e94878dbc128b64fd73580c91ca2d869a9cf",
    "treatment-prompt.txt": "965066611983e57d7206a09100fe84fe91aa669b769d9284ecf1d7e1d103b325",
}


def digest(data):
    return sha256(data).hexdigest()


def compact(data, *, sort=False):
    return json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=sort, allow_nan=False).encode()


def members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def finite_float(value):
    amount = float(value)
    if not math.isfinite(amount):
        raise ValueError("Non-finite JSON number")
    return amount


def invalid_constant(_):
    raise ValueError("Non-finite JSON constant")


def parse(data):
    return json.loads(data, object_pairs_hook=members, parse_constant=invalid_constant, parse_float=finite_float)


def read(path):
    return parse(path.read_bytes())


def number(value, *, integer=False):
    if type(value) is int and value >= 0:
        return value
    if not integer and type(value) is float and math.isfinite(value) and value >= 0:
        return value
    return None


def text_value(value):
    return value if isinstance(value, str) and value and value != "unavailable" else None


def is_run_id(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return value if isinstance(value, list) and all(isinstance(row, dict) for row in value) else []


def verify_inputs():
    paths = {"stage_1_1_package": ARCHIVE.parent / "wpai-exec-stage-1.1.zip",
             "ground_truth.json": SOURCE / "ground_truth.json", "response_schema.json": SOURCE / "response_schema.json",
             **{f"{arm}-prompt.txt": ARCHIVE / f"{arm}-prompt.txt" for arm in TOOLS}}
    if read(ARCHIVE / "identities.json") != IDENTITIES:
        raise ValueError("Frozen Stage 1.2 identity inventory differs")
    for name, path in paths.items():
        if digest(path.read_bytes()) != IDENTITIES[name]:
            raise ValueError(f"Frozen identity differs for {name}")
    template = (SOURCE / "task.txt").read_text(encoding="utf-8")
    for arm in TOOLS:
        instruction = (SOURCE / f"{arm}.txt").read_text(encoding="utf-8").strip()
        if digest(template.replace("{arm_instruction}", instruction).encode()) != IDENTITIES[f"{arm}-prompt.txt"]:
            raise ValueError(f"Prompt source differs for {arm}")

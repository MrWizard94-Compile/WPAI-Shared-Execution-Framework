"""Fixed Stage 1.6 wire contract and frozen synthetic fixture identities."""

from hashlib import sha256
import json
from pathlib import Path
import sys


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
STAGE12 = SOURCE.parent / "stage-1.2"
PACKAGE_HASH = "9063cd629145fee025a6330dd969a6bb608bc2571cca72dde5860947652a3686"
DATASET_HASH = "1eb47cd4ebc554a490b3cc439440f927fced1cc052aa3d634cdd2e97941092f8"
PLAN_HASH = "2655c6732c919abdd7624d36cd12296234f20443e09b78f5f354e5bf29003224"
PROJECT = "fictional-clockwork-museum"
TOOL = "repo_health_v1"
MCP = "2026-07-28"
SCENARIOS = ("normal", "external_termination", "duplicate_writer", "owner_loss")
RESULTS = {
    "normal": ("observed_success", "pass"),
    "external_termination": ("observed_failure", "pass"),
    "duplicate_writer": ("observed_success", "pass"),
    "owner_loss": ("incomplete", "fail_closed"),
}


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(data):
    return sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def unique(rows):
    result = {}
    for key, value in rows:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(_):
    raise ValueError("Nonfinite JSON constant")


def parse(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)


REQUEST = canonical({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                     "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": MCP,
                                         "io.modelcontextprotocol/clientCapabilities": {}},
                                "name": TOOL, "arguments": {"project": PROJECT}}}) + b"\n"
RESPONSE_MARK = {"bytes": 6953, "sha256": "bf90f56726d19364d908a2cf1bc90269ee81e5beffc8c9f41525a30c80f50226"}


def observation(data):
    return {"bytes": len(data), "sha256": digest(data)}


def fixture_input():
    archive = ROOT / "outputs" / "wpai-exec-stage-1.1.zip"
    dataset = (STAGE12 / "ground_truth.json").read_bytes()
    require(digest(archive.read_bytes()) == PACKAGE_HASH and digest(dataset) == DATASET_HASH,
            "Frozen package or dataset identity mismatch")
    return parse(dataset)["facts"]


def prepare(path):
    fixture_input()
    sys.path.insert(0, str(STAGE12))
    try:
        from benchmark import prepare as extract
        entry = extract(path, "treatment")
    finally:
        sys.path.pop(0)
    require(digest(entry.with_name("ground_truth.json").read_bytes()) == DATASET_HASH,
            "Extracted data identity mismatch")
    return entry.parent


def verify_response(frame):
    sys.path.insert(0, str(STAGE12))
    try:
        from benchmark import exact
    finally:
        sys.path.pop(0)
    value = parse(frame)
    require(set(value) == {"jsonrpc", "id", "result"} and value["jsonrpc"] == "2.0"
            and type(value["id"]) is int and value["id"] == 1, "Wrong JSON-RPC reply")
    body = value["result"]
    report = {
        "contract": "wpai.repo_health.v1", "status": "OK", "project": PROJECT,
        "opened_at": "2034-06-18T12:00:00.000Z", "closed_at": "2034-06-18T12:00:00.000Z",
        "facts": fixture_input(), "measurements": {"elapsed_ms": 0, "git_process_attempts": 0,
                                                 "github_get_process_attempts": 0, "provider_usage": "unavailable"},
    }
    require(body["resultType"] == "complete" and body.get("isError", False) is False
            and exact(body["structuredContent"], report)
            and len(body["content"]) == 1 and body["content"][0]["type"] == "text"
            and exact(parse(body["content"][0]["text"]), report), "Frozen synthetic oracle mismatch")
    require(observation(frame) == RESPONSE_MARK, "Frozen response wire identity mismatch")

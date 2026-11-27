"""Reproduce deterministic evidence from four real Windows process scenarios."""

import argparse
import json
from pathlib import Path

from contract import DATASET_HASH, MCP, PACKAGE_HASH, PLAN_HASH, RESULTS, ROOT, SOURCE, TOOL, digest, require
from observer import run_case
from witness import SCHEMA


OUTPUT = ROOT / "outputs" / "stage-1.6"
BASELINE = "b6366372f3a6e877db48616c115d24c6cd05558c"
CONSTITUTION = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"
HISTORY_HASH = "7212ea93f88a1bfb702826d0976694eb6891567bef87e8eefed9817cb3281337"
PRIOR = ("stage-1.2", "stage-1.3", "stage-1.3.1", "stage-1.4", "stage-1.4.1", "stage-1.5")
OUTPUTS = {"historical.sha256", "manifest.sha256", "architecture.md", "handoff.md", "evidence.json"}


def files(directory):
    return {path.relative_to(ROOT).as_posix() for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts}


def inventory(paths):
    return "".join(f"{digest((ROOT / path).read_bytes())}  {path}\n" for path in sorted(paths)).encode("ascii")


def verify_history():
    record = (OUTPUT / "historical.sha256").read_bytes()
    require(digest(record) == HISTORY_HASH, "Historical baseline inventory differs")
    paths = set()
    for stage in PRIOR:
        paths.update(files(ROOT / "work" / "benchmarks" / stage))
        paths.update(files(ROOT / "outputs" / stage))
    require(inventory(paths) == record, "A frozen earlier-stage file or path differs")
    plan_bytes = (ROOT / "outputs/stage-1.3/repeatability-plan.json").read_bytes()
    plan = json.loads(plan_bytes)
    require(digest(plan_bytes) == PLAN_HASH and plan["live_inference_authorized"] is False
            and plan["session_counts"]["authorized_now"] == 0, "Frozen authorization mismatch")
    return len(paths)


def normalized():
    count = verify_history()
    scenarios = {}
    for scenario, expected in RESULTS.items():
        _, result = run_case(scenario)
        require((result.get("lifecycle"), result.get("qualification")) == expected,
                f"{scenario}: {result}")
        scenarios[scenario] = result
    return {
        "schema": "wpai.benchmark.synthetic-split-route-evidence.v1", "witness_schema": SCHEMA,
        "baseline": BASELINE, "constitution": CONSTITUTION, "historical_files_verified": count,
        "fixture": {"package_sha256": PACKAGE_HASH, "dataset_sha256": DATASET_HASH, "operation": TOOL,
                    "protocol": MCP, "facts": 12, "calls_per_case": 1},
        "live_provider_sessions": 0, "authorized_now": 0, "native_provider_qualified": False,
        "scenarios": scenarios,
    }


def ensure(path, data, write):
    if write:
        path.write_bytes(data)
    else:
        require(path.read_bytes() == data, f"{path.name} does not reproduce")


def main():
    options = argparse.ArgumentParser(description=__doc__)
    options.add_argument("--write", action="store_true", help="Regenerate the new evidence and manifest")
    args = options.parse_args()
    evidence = normalized()
    ensure(OUTPUT / "evidence.json",
           (json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8"), args.write)
    manifest = OUTPUT / "manifest.sha256"
    output_paths = files(OUTPUT) - {manifest.relative_to(ROOT).as_posix()}
    require(output_paths == {(OUTPUT / name).relative_to(ROOT).as_posix() for name in OUTPUTS - {manifest.name}},
            "Unexpected Stage 1.6 output inventory")
    entries = files(SOURCE) | output_paths
    ensure(manifest, inventory(entries), args.write)
    print(f"Verified four live synthetic scenarios, {evidence['historical_files_verified']} historical files "
          f"and {len(entries)} Stage 1.6 entries. Authorized provider sessions: 0.")


if __name__ == "__main__":
    main()

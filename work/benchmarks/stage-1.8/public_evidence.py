"""Replay the five real Windows cases and verify the Stage 1.8 publication offline."""

import argparse
from hashlib import sha256
import json
import platform

from boundary import CASES, INJECTED_EXIT, RECOVERY_MS, ROOT, SOURCE
from contract import DATASET_HASH, PACKAGE_HASH, PLAN_HASH, parse, require
from driver import run_case
from journal import SCHEMA, TERMINAL_STATUS, VALID_EXIT


OUTPUT = ROOT / "outputs" / "stage-1.8"
BASE = "59978aae05bd062e9ab93a4dea56a9498a88845f"
CONSTITUTION = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"
HISTORY_HASH = "c8ef256706c7e935d0b722f40ffaacd62eb49c0c0ef34c5f90a4675fd7d214e0"
MATRIX_HASH = "9b9f7e9ffa4e8bb7d9a34c251ff9aac3df797396a7383827a3365e881b8f0559"
STAGES = ("1.2", "1.3", "1.3.1", "1.4", "1.4.1", "1.5", "1.6", "1.7")
OUTPUTS = {"historical.sha256", "evidence.json", "handoff.md", "architecture.md"}
MEASUREMENTS = ("recovery_elapsed_ns", "exit_codes", "controller_ReadFile", "actor_terminal_ReadFile")


def files(directory):
    return {value.relative_to(ROOT).as_posix() for value in directory.rglob("*")
            if value.is_file() and "__pycache__" not in value.parts}


def digest(data):
    return sha256(data).hexdigest()


def inventory(paths):
    return "".join(f"{digest((ROOT / name).read_bytes())}  {name}\n" for name in sorted(paths)).encode("ascii")


def verify_history():
    record = (OUTPUT / "historical.sha256").read_bytes()
    require(digest(record) == HISTORY_HASH, "Historical inventory is not the frozen baseline")
    names = set().union(*(files(ROOT / root / ("stage-" + stage))
                          for root in ("work/benchmarks", "outputs") for stage in STAGES))
    require(inventory(names) == record, "Historical source or evidence differs")
    matrix = (ROOT / "outputs/stage-1.7/isolation-matrix.json").read_bytes()
    plan = (ROOT / "outputs/stage-1.3/repeatability-plan.json").read_bytes()
    require(digest(matrix) == MATRIX_HASH and digest(plan) == PLAN_HASH, "Isolation or repeatability baseline changed")
    authority = parse(matrix)
    require(set(authority["routes"]) == {"codex", "antigravity", "grok"}
            and authority["authorization"]["authorized_now"] == 0
            and all(route["decision"] == "NO-GO" and route["native_qualified"] is False
                    and route["authorized_sessions"] == 0 for route in authority["routes"].values()),
            "A native route or the authority boundary changed")
    return len(names)


def summarize(result):
    normalized = {key: value for key, value in result.items() if key not in MEASUREMENTS}
    return {**normalized, "exit_roles": sorted(result["exit_codes"]),
            "actor_terminal_channels": sorted(result["actor_terminal_ReadFile"]),
            "controller_exit": result["exit_codes"]["controller"], "controller_terminal_observed": True}


def check_reference(reference, summaries):
    require(reference.keys() == {"python", "cases"} and reference["python"] in ("3.10.11", "3.14.3")
            and reference["cases"].keys() == summaries.keys(), "Malformed reference measurement set")
    for case, sample in reference["cases"].items():
        require(sample.keys() == set(MEASUREMENTS), "Unexpected reference measurement fields")
        replay = summaries[case]
        exits, reads = sample["exit_codes"], sample["actor_terminal_ReadFile"]
        require(isinstance(exits, dict) and sorted(exits) == replay["exit_roles"]
                and all(VALID_EXIT(code) for code in exits.values())
                and exits["controller"] == (0 if case == "normal" else INJECTED_EXIT),
                "Reference exit evidence disagrees with reproduced roles")
        require(isinstance(reads, dict) and sorted(reads) == replay["actor_terminal_channels"]
                and all(TERMINAL_STATUS(code) for code in reads.values())
                and TERMINAL_STATUS(sample["controller_ReadFile"]), "Reference terminal observation disagrees")
        duration = sample["recovery_elapsed_ns"]
        if case == "normal":
            require(duration is None and all(code == 0 for code in exits.values()), "Invalid normal reference result")
        else:
            require(type(duration) is int and 0 <= duration <= RECOVERY_MS * 1_000_000,
                    "Reference recovery duration exceeded its bound")


def render(reference=None):
    history = verify_history()
    actual = {case: run_case(case)[1] for case in CASES}
    summaries = {case: summarize(result) for case, result in actual.items()}
    if reference is None:
        reference = {"python": platform.python_version(),
                     "cases": {case: {key: result[key] for key in MEASUREMENTS}
                               for case, result in actual.items()}}
    check_reference(reference, summaries)
    evidence = {
        "schema": "wpai.benchmark.independent-controller-evidence.v1", "journal_schema": SCHEMA,
        "baseline": BASE, "constitution": CONSTITUTION, "historical_files_verified": history,
        "fixture": {"package_sha256": PACKAGE_HASH, "dataset_sha256": DATASET_HASH, "operation": "repo_health_v1"},
        "stage_1_7_matrix_sha256": MATRIX_HASH, "native_routes": dict.fromkeys(("codex", "antigravity", "grok"), "NO-GO"),
        "authorized_now": 0, "live_provider_sessions": 0, "provider_processes_started": 0, "provider_api_calls": 0,
        "account_or_config_changes": 0, "native_qualification_started": False,
        "recovery_deadline_ms": RECOVERY_MS, "validation": "witness_then_driver",
        "scenarios": summaries, "measured_windows_reference": reference,
    }
    return (json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()


def ensure(path, value, write):
    if write:
        path.write_bytes(value)
    else:
        require(path.read_bytes() == value, f"{path.name} does not reproduce")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true", help="Reproduce evidence and manifest using the archived sample")
    modes.add_argument("--capture", action="store_true", help="Capture fresh measured reference values")
    args = parser.parse_args()
    evidence = OUTPUT / "evidence.json"
    reference = None if args.capture else parse(evidence.read_bytes())["measured_windows_reference"]
    ensure(evidence, render(reference), args.write or args.capture)
    manifest = OUTPUT / "manifest.sha256"
    outputs = files(OUTPUT) - {manifest.relative_to(ROOT).as_posix()}
    require(outputs == {(OUTPUT / name).relative_to(ROOT).as_posix() for name in OUTPUTS},
            "Unexpected Stage 1.8 evidence inventory")
    entries = files(SOURCE) | outputs
    ensure(manifest, inventory(entries), args.write or args.capture)
    print(f"Verified five independent-process cases, {verify_history()} frozen files and {len(entries)} Stage 1.8 hashes.")


if __name__ == "__main__":
    main()

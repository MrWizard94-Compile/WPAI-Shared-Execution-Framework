"""Regenerate strict qualification evidence and verify committed Stage 1.4.1 bytes."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from qualify_witness import qualify
from qualification import EXPECTED, run_case
from verify_prior import PRIOR_PREFIXES, ROOT, parse_inventory


SOURCE = Path(__file__).resolve().parent
OUTPUT = ROOT / "outputs" / "stage-1.4.1"
BASELINE = "3526d53e8a29beba6cfb08b28737298a9ff7e1ed"
STAGE_1_4 = "9e667745fe1af1619fbd07d0024d13c887fe083f"
CONSTITUTION = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"


def inventory(paths):
    return "".join(f"{sha256((ROOT / path).read_bytes()).hexdigest()}  {path}\n" for path in sorted(paths)).encode()


def files_in(directory):
    return {file.relative_to(ROOT).as_posix() for file in directory.rglob("*")
            if file.is_file() and "__pycache__" not in file.parts}


def verify_history():
    prior_manifest = OUTPUT / "historical.sha256"
    entries = parse_inventory(prior_manifest.read_text(encoding="ascii"), PRIOR_PREFIXES)
    expected_files = set().union(*(files_in(ROOT / prefix) for prefix in PRIOR_PREFIXES))
    if set(entries) != expected_files or prior_manifest.read_bytes() != inventory(entries):
        raise ValueError("Historical files or SHA-256 inventory differ")
    return len(entries)


def replay():
    verdicts = {}
    with TemporaryDirectory(prefix="wpai-scenario-proof-") as directory:
        for scenario, lifecycle in EXPECTED.items():
            path = Path(directory) / f"{scenario}.jsonl"
            execution = run_case(scenario, path)
            verdict = qualify(path, scenario)
            expected = "incomplete" if scenario == "observer_crash" else "pass"
            if verdict["lifecycle_status"] != lifecycle or verdict["qualification"] != expected:
                raise RuntimeError(f"{scenario}: unexpected strict verdict {verdict}")
            if expected == "incomplete":
                guard = execution["test_parent_after_observer_exit"]
                if guard != {"observer_exit_code": 91, "active": 0}:
                    raise RuntimeError("Crash sentinel or guard evidence differs")
                verdict["separate_crash_guard"] = guard
            verdicts[scenario] = verdict
    return verdicts


def render():
    tracked = verify_history()
    plan = json.loads((ROOT / "outputs/stage-1.3/repeatability-plan.json").read_bytes())
    if plan["live_inference_authorized"] is not False or plan["session_counts"]["authorized_now"] != 0:
        raise ValueError("Frozen plan exceeds the offline authority")
    evidence = {"schema": "wpai.benchmark.lifecycle-scenario-evidence.v1", "baseline": BASELINE,
                "stage_1_4_implementation": STAGE_1_4, "constitution": CONSTITUTION,
                "historical_files_verified": tracked, "native_provider_qualification_started": False,
                "authorized_now": 0, "scenarios": replay()}
    return (json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the new evidence and manifest")
    args = parser.parse_args()
    evidence, manifest = OUTPUT / "evidence.json", OUTPUT / "manifest.sha256"
    expected = render()
    if args.write:
        evidence.write_bytes(expected)
    elif evidence.read_bytes() != expected:
        raise SystemExit("Stage 1.4.1 evidence differs from replayed scenario verdicts")
    files = files_in(SOURCE) | files_in(OUTPUT)
    files.discard(manifest.relative_to(ROOT).as_posix())
    expected = inventory(files)
    if args.write:
        manifest.write_bytes(expected)
    elif manifest.read_bytes() != expected:
        raise SystemExit("Stage 1.4.1 manifest differs from the exact deliverables")
    print(f"Verified 13 replayed scenario verdicts and {len(files)} Stage 1.4.1 manifest entries.")


if __name__ == "__main__":
    main()

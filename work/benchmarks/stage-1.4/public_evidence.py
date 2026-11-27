"""Reproduce the normalized witness evidence and verify the complete SHA-256 inventory."""

import argparse
import json
from pathlib import Path, PurePosixPath

from qualification import qualify
from witness_record import digest, token


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
OUTPUT = ROOT / "outputs" / "stage-1.4"
BASE = "a4dbdb46ddcac40ee701773e328b725cb0eba954"
LAW = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"
PRIOR = ("work/benchmarks/stage-1.2", "work/benchmarks/stage-1.3", "work/benchmarks/stage-1.3.1",
         "outputs/stage-1.2", "outputs/stage-1.3", "outputs/stage-1.3.1")


def files_in(directory):
    return {path.relative_to(ROOT).as_posix() for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts}


def sha256s(paths):
    return "".join(f"{digest((ROOT / path).read_bytes())}  {path}\n" for path in sorted(paths)).encode()


def verify_history():
    path = OUTPUT / "historical.sha256"
    allowed = set().union(*(files_in(ROOT / directory) for directory in PRIOR))
    listed = set()
    for line in path.read_text(encoding="ascii").splitlines():
        checksum, name = line.split("  ", 1)
        relative = PurePosixPath(name)
        if (not token(checksum) or relative.is_absolute() or ".." in relative.parts
                or relative.as_posix() != name or name not in allowed or name in listed):
            raise ValueError("Unexpected historical digest path")
        listed.add(name)
    if listed != allowed or path.read_bytes() != sha256s(listed):
        raise ValueError("Historical inventory or file bytes differ")
    return len(listed)


def render():
    count = verify_history()
    plan = json.loads((ROOT / "outputs" / "stage-1.3" / "repeatability-plan.json").read_bytes())
    if plan["live_inference_authorized"] is not False or plan["session_counts"]["authorized_now"] != 0:
        raise ValueError("Frozen repeatability plan exceeds Stage 1.4 authority")
    evidence = {
        "schema": "wpai.benchmark.lifecycle-witness-qualification.v1",
        "baseline": {"repository": "MrWizard94-Compile/WPAI-Shared-Execution-Framework", "branch": "main", "sha": BASE,
                     "constitution": LAW, "constitution_version": "6.24.0", "historical_files_verified": count},
        "scope": "Offline synthetic witness evidence. Runtime identities, timestamps, and chain hashes are validated before normalization.",
        "live_inference_authorized": False, "native_provider_qualification_started": False,
        "frozen_plan_session_counts": plan["session_counts"], "scenarios": qualify(),
    }
    return (json.dumps(evidence, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate only Stage 1.4 normalized evidence and manifest")
    args = parser.parse_args()
    evidence = OUTPUT / "evidence.json"
    manifest = OUTPUT / "manifest.sha256"
    reproduced = render()
    if args.write:
        evidence.write_bytes(reproduced)
    elif evidence.read_bytes() != reproduced:
        raise SystemExit("Stage 1.4 normalized evidence differs from the observed runs")
    paths = files_in(SOURCE) | files_in(OUTPUT) | {".github/workflows/tests.yml"}
    paths.discard(manifest.relative_to(ROOT).as_posix())
    expected = sha256s(paths)
    if args.write:
        manifest.write_bytes(expected)
    elif manifest.read_bytes() != expected:
        raise SystemExit("Stage 1.4 SHA-256 inventory differs")
    print(f"Reproduced Stage 1.4 evidence and verified {len(paths)} manifest entries.")


if __name__ == "__main__":
    main()

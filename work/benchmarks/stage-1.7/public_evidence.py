"""Reproduce Stage 1.7 evidence and verify historical and publication hashes offline."""

import argparse
from hashlib import sha256

from isolation_matrix import OUTPUT, ROOT, SOURCE, guard_public, render, require


PRIOR_STAGES = ("stage-1.2", "stage-1.3", "stage-1.3.1", "stage-1.4", "stage-1.4.1", "stage-1.5", "stage-1.6")
HISTORY_SHA = "84671dfea75c3221adcaf2cfa634d1fe4b38c86c714893d1f10594de16afcc76"
OUTPUT_NAMES = {"isolation-matrix.json", "route-assessment.md", "future-preflight-decisions.md",
                "handoff.md", "historical.sha256"}


def files(directory):
    return {path.relative_to(ROOT).as_posix() for path in directory.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts}


def inventory(paths):
    return "".join(f"{sha256((ROOT / path).read_bytes()).hexdigest()}  {path}\n"
                   for path in sorted(paths)).encode("ascii")


def verify_history():
    original = (OUTPUT / "historical.sha256").read_bytes()
    require(sha256(original).hexdigest() == HISTORY_SHA, "Historical inventory differs from the accepted baseline")
    paths = set().union(*(files(ROOT / prefix / stage)
                          for prefix in ("work/benchmarks", "outputs") for stage in PRIOR_STAGES))
    require(inventory(paths) == original, "Historical file paths or contents differ from the accepted baseline")
    return len(paths)


def ensure(path, value, write):
    if write:
        path.write_bytes(value)
    else:
        require(path.read_bytes() == value, f"{path.name} differs from verification")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the new matrix and manifest")
    args = parser.parse_args()
    count = verify_history()
    ensure(OUTPUT / "isolation-matrix.json", render(), args.write)
    manifest = OUTPUT / "manifest.sha256"
    outputs = files(OUTPUT) - {manifest.relative_to(ROOT).as_posix()}
    require(outputs == {(OUTPUT / item).relative_to(ROOT).as_posix() for item in OUTPUT_NAMES},
            "Unexpected Stage 1.7 output inventory")
    for name in outputs:
        if name.endswith(".md"):
            guard_public((ROOT / name).read_text(encoding="utf-8"))
    entries = files(SOURCE) | outputs
    ensure(manifest, inventory(entries), args.write)
    print(f"Verified {count} frozen files, {len(entries)} Stage 1.7 entries and zero provider authorization.")


if __name__ == "__main__":
    main()

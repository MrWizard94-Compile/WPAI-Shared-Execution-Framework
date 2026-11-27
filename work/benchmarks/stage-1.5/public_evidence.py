"""Verify Stage 1.5 publication and reproduce its static route matrix."""

import argparse
from hashlib import sha256
from pathlib import Path

from route_matrix import OUTPUT, ROOT, SOURCE, render, require, validate_public_text


PRIOR = ("stage-1.2", "stage-1.3", "stage-1.3.1", "stage-1.4", "stage-1.4.1")
PRIOR_DIGEST = "c3c963f7a088128ed5e57e8d61e6f363d56710c8b8b83627237964510bcae34b"
OUTPUT_FILES = {"route-matrix.json", "route-assessment.md", "qualification-plan.md",
                "handoff.md", "historical.sha256", "manifest.sha256"}


def files_in(directory):
    return {file.relative_to(ROOT).as_posix() for file in directory.rglob("*")
            if file.is_file() and "__pycache__" not in file.parts}


def inventory(paths):
    return "".join(f"{sha256((ROOT / path).read_bytes()).hexdigest()}  {path}\n"
                   for path in sorted(paths)).encode("ascii")


def verify_history():
    record = (OUTPUT / "historical.sha256").read_bytes()
    require(sha256(record).hexdigest() == PRIOR_DIGEST, "Historical inventory is not the frozen baseline")
    paths = set()
    for stage in PRIOR:
        paths.update(files_in(ROOT / "work" / "benchmarks" / stage))
        paths.update(files_in(ROOT / "outputs" / stage))
    require(inventory(paths) == record, "Historical content or file inventory changed")
    return len(paths)


def replace_or_verify(path: Path, expected: bytes, write: bool):
    if write:
        path.write_bytes(expected)
    else:
        require(path.read_bytes() == expected, f"{path.name}: committed bytes differ from reproduction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Reproduce the new matrix and manifest only")
    args = parser.parse_args()
    count = verify_history()
    replace_or_verify(OUTPUT / "route-matrix.json", render(), args.write)
    output_files = files_in(OUTPUT)
    manifest = OUTPUT / "manifest.sha256"
    manifest_path = manifest.relative_to(ROOT).as_posix()
    output_files.discard(manifest_path)
    expected_outputs = {(OUTPUT / name).relative_to(ROOT).as_posix()
                        for name in OUTPUT_FILES if name != manifest.name}
    require(output_files == expected_outputs, "Stage 1.5 output set differs")
    for path in output_files:
        if path.endswith(".md"):
            validate_public_text((ROOT / path).read_text(encoding="utf-8"), plan=path.endswith("qualification-plan.md"))
    files = files_in(SOURCE) | output_files
    replace_or_verify(manifest, inventory(files), args.write)
    print(f"Verified {count} frozen files and {len(files)} Stage 1.5 entries. Authorized sessions: 0.")


if __name__ == "__main__":
    main()

"""Run the unchanged Stage 1.4 verifier with its exact historical workflow bytes."""

from hashlib import sha256
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ".github/workflows/tests.yml"
BOUNDARY = b"      - name: Verify Stage 1.4.1 scenario-specific witness completeness"
DISPATCH = b"          python -B -W error work/benchmarks/stage-1.4.1/verify_prior.py"
LEGACY_DISPATCH = b"          python -B -W error work/benchmarks/stage-1.4/public_evidence.py"
PRIOR_STAGES = ("stage-1.2", "stage-1.3", "stage-1.3.1", "stage-1.4")
PRIOR_PREFIXES = tuple(f"{parent}/{stage}/" for parent in ("work/benchmarks", "outputs") for stage in PRIOR_STAGES)
PACKAGE = "outputs/wpai-exec-stage-1.1.zip"


def parse_inventory(text, prefixes, extra=()):
    entries = {}
    for line in text.splitlines():
        checksum, name = line.split("  ", 1)
        path = PurePosixPath(name)
        if (not re.fullmatch(r"[0-9a-f]{64}", checksum) or path.is_absolute() or ".." in path.parts
                or str(path) != name or "\\" in name or ":" in name or name in entries
                or (name not in extra and not name.startswith(prefixes))):
            raise ValueError("Unexpected manifest entry")
        entries[name] = checksum
    return entries


def historical_workflow(current, manifest):
    workflow, boundary, _ = current.partition(BOUNDARY)
    expected = [line.split("  ", 1)[0] for line in manifest.splitlines() if line.endswith("  " + WORKFLOW)]
    if not boundary or current.count(BOUNDARY) != 1 or workflow.count(DISPATCH) != 1:
        raise ValueError("Unexpected Stage 1.4 workflow dispatch")
    workflow = workflow.replace(DISPATCH, LEGACY_DISPATCH, 1)
    if expected != [sha256(workflow).hexdigest()]:
        raise ValueError("Could not recover the exact Stage 1.4 workflow prefix")
    return workflow


def verify():
    manifest_path = "outputs/stage-1.4/manifest.sha256"
    manifest = (ROOT / manifest_path).read_text(encoding="ascii")
    history = (ROOT / "outputs/stage-1.4/historical.sha256").read_text(encoding="ascii")
    workflow = historical_workflow((ROOT / WORKFLOW).read_bytes(), manifest)
    files = parse_inventory(manifest, PRIOR_PREFIXES, (WORKFLOW,)) | parse_inventory(history, PRIOR_PREFIXES)
    del files[WORKFLOW]
    with TemporaryDirectory(prefix="wpai-witness-prior-") as directory:
        snapshot = Path(directory)
        for relative in sorted(set(files) | {manifest_path, PACKAGE}):
            source = ROOT / relative
            if not source.resolve().is_relative_to(ROOT):
                raise ValueError("Historical file resolves outside the checkout")
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if relative in files and sha256(target.read_bytes()).hexdigest() != files[relative]:
                raise ValueError(f"Historical file hash differs for {relative}")
        workflow_file = snapshot / WORKFLOW
        workflow_file.parent.mkdir(parents=True)
        workflow_file.write_bytes(workflow)
        subprocess.run([sys.executable, "-B", "-W", "error", "work/benchmarks/stage-1.4/public_evidence.py"],
                       cwd=snapshot, check=True, timeout=90)


if __name__ == "__main__":
    verify()

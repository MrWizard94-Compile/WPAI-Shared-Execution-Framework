"""Measure repeatability of the released W1 operation with fresh local MCP processes."""

from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZipFile
import importlib.util
import json
import statistics
import sys


WORK = Path(__file__).resolve().parent
OUT = WORK.parent / "outputs"
ARCHIVE = OUT / "wpai-exec-stage-1.zip"
DIGEST = "e59195bbf15d172efdb085728efd4c265a86305df391d688eed2ee38255c490a"


def verified_harness(extracted):
    spec = importlib.util.spec_from_file_location("w1_evidence", WORK / "verify-stage-1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SERVER = extracted / "wpai_exec.py"
    module.SERVER_ARGS = [sys.executable, "-B", str(module.SERVER), "stdio"]
    return module


def contents(value):
    if isinstance(value, dict):
        return {k: contents(v) for k, v in value.items() if k != "observed_at"}
    if isinstance(value, list):
        return [contents(v) for v in value]
    return value


def main():
    assert sha256(ARCHIVE.read_bytes()).hexdigest() == DIGEST
    scratch = Path(mkdtemp(prefix="stage1-repeat-", dir=WORK))
    with ZipFile(ARCHIVE) as package:
        assert package.testzip() is None
        package.extractall(scratch)
    extracted = scratch / "wpai-exec"
    harness = verified_harness(extracted)
    before = harness.fingerprint()
    results = []
    snapshot = None
    for trial_number in range(1, 4):
        path = scratch / f"trial-{trial_number}"
        path.mkdir()
        trial = harness.direct(path, True)
        result = trial["health"]
        oracle = harness.independent_comparison(result)
        assert oracle["matches"] and all(oracle["matches"].values())
        assert result["facts"]["04_working_tree"]["value"] == "clean", "strict clean cohort mismatch"
        assert before == harness.fingerprint(), "Git metadata changed during the cohort"
        current = contents(result["facts"])
        if snapshot is None:
            snapshot = current
        assert snapshot == current, "W1 observable facts changed during the cohort"
        results.append({"trial": trial_number, "opened_at": result["opened_at"],
                        **result["measurements"], "w1_fields_matched": len(oracle["matches"]),
                        "main_sha": oracle["main_sha"], "result_bytes": trial["bytes"],
                        "probe_shutdown_exit": trial["process"]["exit"]})
    summary = {"package_sha256": DIGEST, "protocol": "2026-07-28", "fresh_server_process_per_trial": True,
               "ci_scope": "same reported CI surfaces, checked independently after each trial",
               "git_metadata_unchanged": True, "git_metadata_files": len(before),
               "trials": results, "median_elapsed_ms": statistics.median(row["elapsed_ms"] for row in results)}
    report = scratch / "repeatability.json"
    report.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(report)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

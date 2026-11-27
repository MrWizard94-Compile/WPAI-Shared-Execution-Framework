from difflib import unified_diff
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp


BASE = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"
CANONICAL = Path("C:/WPAI/WPAI Constitution")
WORK = Path(__file__).resolve().parent
OUT = WORK.parent / "outputs" / "wpai-constitution-measurement-proposal.patch"
snapshot = Path(mkdtemp(prefix="stage1-evolution-", dir=WORK))
subprocess.run(["git", "clone", "--local", "--no-hardlinks", "--no-checkout", "--no-tags",
                str(CANONICAL), str(snapshot)], check=True)
subprocess.run(["git", "switch", "--detach", BASE], cwd=snapshot, check=True)

engineering = "law/ENGINEERING.md"
changelog = "CHANGELOG.md"
ledger = "evolution/LEDGER.md"
version = "6.24.1"
old = "6.24.0"


def replace(path, needle, replacement):
    source = (snapshot / path).read_text(encoding="utf-8")
    if needle not in source:
        raise ValueError(f"Unrecognized source in {path}")
    return source, source.replace(needle, replacement, 1)


heading = "### PERF-BUDGET-001 — Real constraints"
measurement = (
    "When a benchmark crosses wrapper, subprocess, remote service, or provider\n"
    "boundaries, give each reported metric a unit, observation boundary, and\n"
    "provenance. Keep visible invocations, attempted subprocess launches, and\n"
    "observed remote operations distinct. Mark derived, estimated, and unavailable\n"
    "telemetry explicitly. Compare savings only across equivalent workloads,\n"
    "boundaries, and observation windows.\n\n"
)
entry = (
    "## 2026-11-26 — Preserve benchmark measurement boundaries\n\n"
    "**Observed gap:** a repository-health benchmark had one visible invocation,\n"
    "multiple Git and API-command attempts, and no model-usage telemetry. A single\n"
    "operation count cannot describe all three measurement boundaries.\n\n"
    "**Meaningful change:** extend `PERF-REASON-001` with unit, boundary, and\n"
    "provenance for cross-boundary benchmark metrics and require equivalent\n"
    "observations for savings claims.\n\n"
    "**Falsification:** present two trials with equal visible invocations, different\n"
    "process counts, and unknown provider usage. A conforming report preserves\n"
    "both measured counts, identifies unavailable usage, and withholds the savings\n"
    "claim if the measurement boundaries or windows differ.\n\n"
    f"**Boundary:** apply-ready proposal based on `{BASE}`.\n\n"
)
changes = {
    engineering: replace(engineering, heading, measurement + heading),
    changelog: replace(changelog, "# Changelog\n\n", "# Changelog\n\n"
                       f"## {version} — 2026-11-26 (proposal)\n\n"
                       "- Clarify benchmark provenance across wrapper, process, remote service,\n"
                       "  and provider boundaries under `PERF-REASON-001`.\n\n"),
    ledger: replace(ledger, "## 2026-11-23", entry + "## 2026-11-23"),
    "SKILL.md": replace("SKILL.md", f'skill-version: "{old}"', f'skill-version: "{version}"'),
    "SOURCE.json": replace("SOURCE.json", f'"skill_version": "{old}"', f'"skill_version": "{version}"'),
    "VERSION": replace("VERSION", old, version),
}
patch = snapshot / "proposal.patch"
patch.write_bytes("".join(line for name, (before, after) in sorted(changes.items())
                          for line in unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                                   fromfile=f"a/{name}", tofile=f"b/{name}")).encode())
subprocess.run(["git", "apply", "--check", str(patch)], cwd=CANONICAL, check=True)
subprocess.run(["git", "apply", str(patch)], cwd=snapshot, check=True)
subprocess.run([sys.executable, "-X", "utf8", "-B", "tools/validate-source.py"], cwd=snapshot, check=True)
with (snapshot / "tests.log").open("wb") as log:
    subprocess.run([sys.executable, "-X", "utf8", "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                   cwd=snapshot, stdout=log, stderr=subprocess.STDOUT, check=True)
assert measurement in (snapshot / engineering).read_text(encoding="utf-8")
OUT.write_bytes(patch.read_bytes())
print(snapshot)
print((snapshot / "tests.log").read_text(encoding="utf-8", errors="replace").splitlines()[-4:])

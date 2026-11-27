from hashlib import sha256
import json
from pathlib import Path


WORK = Path(__file__).resolve().parent
OUT = WORK.parent / "outputs"
PACKAGE = OUT / "wpai-exec-stage-1.zip"
PATCH = OUT / "wpai-constitution-measurement-proposal.patch"
REVIEW = OUT / "wpai-stage-1-w1.md"
RUN = WORK / "stage1-verify-kqv25u3r"
BUILD = WORK / "stage1-package-_559rxjp"
EVOLUTION = WORK / "stage1-evolution-hth4rwom"
BASE = "0adf5ecee5f7f96ce3749944dc097a003731a6e9"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


checks = read(RUN / "comparison.json")
routes = read(RUN / "routes.json")
build = read(BUILD / "package.json")
assert len(checks["oracle"]["matches"]) == 12 and all(checks["oracle"]["matches"].values())
assert checks["git_metadata_unchanged"] and build["archive_sha256"] == digest(PACKAGE)
assert build["cli_observed_fields"] == 12 and build["cli_denial_exit"] == 2
assert all(route["process"] == {"exit": 0, "forced": False} for route in routes.values())
assert all(route["denial"]["status"] == "DENIED" for route in routes.values())
assert (EVOLUTION / "tests.log").read_text(encoding="utf-8").rstrip().endswith("OK (skipped=1)")
candidate = "wpai-exec-stage-1.zip sha256=" + digest(PACKAGE)


def evidence(identity, kind, reference):
    return {"id": identity, "kind": kind, "subject": candidate, "reference": reference}


sources = [
    evidence("scope", "authorization", "Stage 0C attachment section 7 and Human Director: Note the gap for far future work and continue."),
    evidence("law", "source", f"Live canonical main and frozen checker verified {BASE}; source v6.24.0 and 23 binding files."),
    evidence("design", "analysis", "Single allowlisted project, one adapter, independent identities, fixed subprocess/API operations, no credentials in reports."),
    evidence("unit", "source", f"{BUILD / 'unittest.log'}; 10 tests each with Python 3.10 and 3.14 and -W error."),
    evidence("oracle", "runtime", f"{RUN / 'comparison.json'}; 12 independently matched W1 fields and 11 unchanged Git metadata fingerprints."),
    evidence("routes", "runtime", f"{RUN / 'routes.json'}; same packaged server via both direct stdio eras and isolated Codex app-server profiles."),
    evidence("artifact", "package", f"{BUILD / 'package.json'}; exact, reproducible archive members and CLI replay from extracted package."),
    evidence("handoff", "review", f"{REVIEW} sha256={digest(REVIEW)}; reviewed against the 12 W1 statuses, package, scope and limitations."),
    evidence("patch", "source", f"{PATCH} sha256={digest(PATCH)}; apply-check, source validator, detached-copy tests in {EVOLUTION / 'tests.log'}."),
]

stages = [
    ("done", "Read exact Stage 0C attachment, accepted continuation and W1 objective", ["scope", "law"]),
    ("done", "Verified the production checkout, allowed repo ID, frozen governance and local executables", ["law", "oracle"]),
    ("done", "Reviewed the local execution and dual-era protocol contract", ["design", "routes"]),
    ("done", "Scoped the first slice, chose isolated local handoff and identified acceptance classes", ["scope", "design"]),
    ("done", "Built one CLI and one dual-era MCP service for repo_health_v1", ["artifact", "unit"]),
    ("done", "Verified extracted entry points, failure paths and all twelve field comparisons", ["unit", "oracle", "routes", "artifact"]),
    ("done", "Audited read-only behavior, package integrity and benchmark provenance", ["design", "oracle", "handoff"]),
    ("done", "Prepared the archive, reproducible manifest, report and limits", ["handoff", "artifact"]),
    ("na", "Remote publication and normal client installation were outside this local handoff", ["scope"]),
    ("done", "Verified the delivered paths and staged one validated Constitution change", ["artifact", "handoff", "patch"]),
]
criteria = [
    ("w1", "All 12 W1 dispositions match independent Git and GitHub evidence", ["runtime"], ["oracle", "routes"]),
    ("adapter", "One extracted MCP entry point responds through both eras and Codex client routes", ["package", "runtime"], ["artifact", "routes"]),
    ("limits", "Server-side pre-launch authorization, timeout, size handling and bounded read-only acquisition", ["source", "runtime"], ["unit", "oracle", "routes"]),
    ("delivery", "Reproducible local package with exact W1 objective, usage and verification notes", ["package", "review"], ["artifact", "handoff"]),
]
gate = [
    ("pass", "Twelve purpose-fit fields and CLI/MCP entry points", ["oracle", "routes", "artifact"]),
    ("pass", "Python, Git and GitHub CLI verified on Windows", ["unit", "routes"]),
    ("pass", "Ten tests on each owned runtime with warnings as errors", ["unit"]),
    ("pass", "Authorization, absence, failure metadata, deadlines, overflow and cancellation tested", ["unit", "oracle", "routes"]),
    ("pass", "README, manifest, W1 and actual results agree", ["artifact", "handoff"]),
    ("pass", "Scoped private read access and subprocess denial reviewed", ["design", "unit", "oracle"]),
    ("pass", "Measured live time, process attempts, payload size and caps", ["routes", "unit"]),
    ("pass", "Declared Python and local protocol support exercised", ["unit", "routes"]),
    ("pass", "Deterministic archive plus extracted tests and runtime", ["artifact", "routes"]),
    ("pass", "Existing tooling and credentials, no model inference or purchases", ["scope", "handoff"]),
    ("pass", "Two package builds matched and source manifest verified", ["artifact"]),
    ("pass", "Original implementation follows documented protocols and uses stdlib only", ["design", "artifact"]),
    ("na", "Single owner and no multi-agent implementation integration", ["scope"]),
    ("pass", "Package manifest, commands, evidence and gap documented", ["artifact", "handoff"]),
    ("pass", "Four-line audit below refers to observed boundaries", ["oracle", "handoff", "routes"]),
]
record = {
    "schema": 1, "invocation": "wpai-stage-1-w1-2026-11-26", "law_sha": BASE,
    "scope": "Local package for the first allowlisted read-only W1 operation after the director accepted deferring Claude. Stage 0C four-client completion remains open.",
    "candidate": candidate, "claim": "complete",
    "stages": [{"stage": index, "status": status, "reason": reason, "evidence": refs}
               for index, (status, reason, refs) in enumerate(stages, 1)],
    "acceptance": [{"id": identity, "criterion": criterion, "status": "pass", "required_evidence": kinds, "evidence": refs}
                   for identity, criterion, kinds, refs in criteria],
    "section0": [{"item": index, "status": status, "reason": reason, "evidence": refs}
                 for index, (status, reason, refs) in enumerate(gate, 1)],
    "evidence": sources, "evolution": {"status": "staged", "evidence": ["patch"]},
    "self_audit": [
        "Twelve live values agreed with independent commands for the final observation window.",
        "Both protocol eras and Codex isolated profiles returned matching text and structured values.",
        "Git metadata fingerprints agreed and a denied project never constructed the reader.",
        "Provider telemetry and live failure causes were unavailable. Claude remains deferred and remote deployment was outside the scope.",
    ],
    "remaining": ["Stage 0C: retest Claude only when eligible subscription and director approval are available.",
                  "Constitution proposal requires later review and independent acceptance before adoption."],
}
(WORK / "wpai-stage-1-workflow-record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
summary = {"package_sha256": digest(PACKAGE), "oracle": checks,
           "live_w1": routes["direct_modern"]["health"],
           "routes": {name: {key: result[key] for key in ("catalog", "denial", "bytes", "process")}
                      for name, result in routes.items()}}
(OUT / "wpai-stage-1-w1-evidence.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

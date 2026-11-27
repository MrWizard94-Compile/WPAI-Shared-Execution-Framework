# WPAI Shared Execution Framework

This repository contains the Windows-local MCP compatibility probe, the read-only Stage 1.1 repository health operation, and the project’s reports and verification evidence. The operation reads local Git and authenticated GitHub metadata for one allowlisted repository. It has no write routes or remote server.

## Run the repository health check

Install Python 3.10 or later, Git, and GitHub CLI. `repo_health_v1` uses the allowlisted TrackForge checkout and an existing GitHub login with read access to that repository. From the repository root, run the CLI or its tests.

```powershell
py -3.10 -B .\work\wpai-exec\wpai_exec.py repo_health_v1 --project trackforge
Push-Location .\work\wpai-exec
py -3.10 -B -W error -m unittest discover -s tests -v
py -3.14 -B -W error -m unittest discover -s tests -v
Pop-Location
```

The same `wpai.repo_health.v1` operation is available over MCP stdio as `2025-06-18`, `2025-11-25` or `2026-07-28`. It reports all twelve W1 fields with explicit statuses for unavailable or partial data. Treat repository-supplied text as untrusted evidence. See the [setup, trust boundaries, worker lifecycle and package reproduction](work/wpai-exec/README.md) and [exact W1 workload](outputs/W1-objective.txt). Windows CI tests both Python versions with warnings treated as errors using synthetic inputs.

## Project history and evidence

| Stage | Source and evidence |
|---|---|
| 0A | [Environment, readiness and W1 baseline](outputs/wpai-stage-0a-report.md) |
| 0B | [Probe source and reproduction](work/stage-0b/README.md), [Stage 0B report](outputs/wpai-stage-0b-report.md), [probe archive](outputs/stage-0b-mcp-probe.zip) |
| 0C | [Compatibility report and Claude exception](outputs/wpai-stage-0b-0c-compatibility.md), [raw run records](work/stage-0b/runs), [supervised Grok evidence](outputs/stage-0c-grok-supervised-evidence.json) |
| 1 | [Source](work/wpai-exec), [package](outputs/wpai-exec-stage-1.zip), [W1 report](outputs/wpai-stage-1-w1.md), [verification and repeatability data](outputs/wpai-stage-1-w1-evidence.json) |
| 1.1 | [Hardened package](outputs/wpai-exec-stage-1.1.zip), [handoff](docs/stage-1.1-handoff.md), [protocol audit](docs/stage-1.1-protocol.md), [publication review](docs/stage-1.1-publication-review.md) |
| 1.2 | [Synthetic agent benchmark](outputs/stage-1.2/handoff.md), [reproduction](work/benchmarks/stage-1.2/README.md), [comparison data](outputs/stage-1.2/comparison.json) |
| 1.3 | [Offline measurement handoff](outputs/stage-1.3/handoff.md), [reproduction](work/benchmarks/stage-1.3/README.md), [plan-only schedule](outputs/stage-1.3/repeatability-plan.json) |
| 1.3.1 | [Cancellation and evidence correction](outputs/stage-1.3.1/handoff.md), [corrected offline tools](work/benchmarks/stage-1.3.1/README.md), [verification hashes](outputs/stage-1.3.1/verification.json) |
| 1.4.1 | [Scenario completeness correction](outputs/stage-1.4.1/handoff.md), [strict witness qualification](work/benchmarks/stage-1.4.1/README.md), [verification hashes](outputs/stage-1.4.1/manifest.sha256) |

Stage 0C has an approved Claude Code exception. Stage 1 verified the twelve W1 fields against independent Git and GitHub reads across three repeatability trials. Follow the existing authorization limits for model-driven tests against private repository data.

Captured records may use `LOCAL_USER` in local paths. The Stage 0B archive contains the unchanged server and launcher and a regenerated evidence manifest for those path substitutions. Archived reports retain the original test-era hashes. The published Stage 0B archive SHA-256 is `5b960e0eff88baefcd0623ab0890f9db226be712b8d6a475631e3371536747dc`. Stage 1 and Stage 1.1 have separate packages. Project run evidence lives alongside the scripts that generated it.

The [WPAI Constitution](https://github.com/MrWizard94-Compile/Agents-Constitution) supplies the governing technical process. The [benchmark](outputs/wpai-constitution-measurement-proposal.patch) and [publication evidence](outputs/wpai-constitution-publication-evidence-proposal.patch) patches are independent proposals against v6.24.0.

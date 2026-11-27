# WPAI Shared Execution Framework

This repository contains the Windows-local MCP compatibility probe, the read-only Stage 1 repository health operation, and the project’s reports and verification evidence.

## Run the repository health check

Install Python 3.10 or later, Git, and GitHub CLI. `repo_health_v1` uses the allowlisted TrackForge checkout and an existing GitHub login with read access to that repository. From the repository root, run the CLI or its tests.

```powershell
py -3.10 -B .\work\wpai-exec\wpai_exec.py repo_health_v1 --project trackforge
Push-Location .\work\wpai-exec
py -3.10 -B -W error -m unittest discover -s tests -v
Pop-Location
```

The same operation is available over MCP stdio. It reports all twelve W1 fields with explicit statuses for unavailable or partial data. See the [MCP setup and runtime limits](work/wpai-exec/README.md) and [exact W1 workload](outputs/W1-objective.txt).

## Project history and evidence

| Stage | Source and evidence |
|---|---|
| 0A | [Environment, readiness and W1 baseline](outputs/wpai-stage-0a-report.md) |
| 0B | [Probe source and reproduction](work/stage-0b/README.md), [Stage 0B report](outputs/wpai-stage-0b-report.md), [probe archive](outputs/stage-0b-mcp-probe.zip) |
| 0C | [Compatibility report and Claude exception](outputs/wpai-stage-0b-0c-compatibility.md), [raw run records](work/stage-0b/runs), [supervised Grok evidence](outputs/stage-0c-grok-supervised-evidence.json) |
| 1 | [Source](work/wpai-exec), [package](outputs/wpai-exec-stage-1.zip), [W1 report](outputs/wpai-stage-1-w1.md), [verification and repeatability data](outputs/wpai-stage-1-w1-evidence.json) |

Stage 0C has an approved Claude Code exception. Stage 1 verified the twelve W1 fields against independent Git and GitHub reads across three repeatability trials. Follow the existing authorization limits for model-driven tests against private repository data.

Captured records may use `LOCAL_USER` in local paths. The Stage 0B archive contains the unchanged server and launcher and a regenerated evidence manifest for those path substitutions. Archived reports retain the original test-era hashes. The published archive SHA-256 is `5b960e0eff88baefcd0623ab0890f9db226be712b8d6a475631e3371536747dc`. The Stage 1 archive is byte-identical to the tested package. Project run evidence lives alongside the scripts that generated it. Account profiles, local application databases, vendor installer caches and disposable dependency copies remain local.

The [WPAI Constitution](https://github.com/MrWizard94-Compile/Agents-Constitution) supplies the governing technical process. The [benchmark](outputs/wpai-constitution-measurement-proposal.patch) and [publication evidence](outputs/wpai-constitution-publication-evidence-proposal.patch) patches are independent proposals against v6.24.0.

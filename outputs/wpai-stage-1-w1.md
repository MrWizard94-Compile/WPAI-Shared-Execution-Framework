# WPAI Stage 1 repository health check

Version 0.1.0 implements `repo_health_v1` for the allowlisted TrackForge checkout and GitHub repository. The package contains the local CLI, one dual-era MCP stdio server, regression tests, a hash manifest and the unchanged W1 objective. The package SHA-256 is `e59195bbf15d172efdb085728efd4c265a86305df391d688eed2ee38255c490a`.

## TrackForge results

The packaged server captured this snapshot on November 26, 2026 at 10:30 p.m. EST. Separate Git commands and GitHub reads agreed on all twelve W1 fields.

| W1 field | Verified observation |
|---|---|
| 1. Repository identity | Private `MrWizard94-Compile/TrackForge`, GitHub repository ID `1351477573`. Local `origin` resolved to the same repository. |
| 2. Local branch and HEAD | `staging` at `b26b56ab554180ad00feb36d83a84938e60aad5d`. |
| 3. Live `main` | `b26b56ab554180ad00feb36d83a84938e60aad5d`, confirmed by GitHub REST and Git `ls-remote`. |
| 4. Working tree | Clean in this snapshot. |
| 5. Change counts | 0 staged, 0 unstaged, 0 untracked and 0 conflicted. |
| 6. Branch inventory | Local `main` and `staging`, cached `origin/main` and `origin/staging`, and live `main` and `staging` all pointed to the same commit. Cached `origin/HEAD` pointed to `origin/main`. |
| 7. Divergence | Local `main` and active `staging` were each 0 ahead and 0 behind live `main`. |
| 8. Recent commits | The five SHAs agreed across local and remote history, from `b26b56ab` through `4f0e6e2b`, `bba3e4b2`, `df23dbe4`, and `df6ee313`. |
| 9. Open pull requests | 0. |
| 10. GitHub Actions | 0 workflows, 0 runs on both inspected branches, and 0 check runs or legacy statuses on the shared head SHA. |
| 11. Failures and causes | No failed checks in the inspected sources. Synthetic regressions verified failed-step evidence and an explicit unavailable root cause where provider metadata was inconclusive. |
| 12. Discrepancies | None for the sampled local and live refs or the working tree. An earlier run captured 3 unstaged changes and 1 untracked file, which independent commands confirmed at that time. |

The live comparison fingerprinted 11 Git metadata files, including the index, configuration, and refs. Their content and modification times agreed before and after the verification window.

## Package and runtime verification

- Two independent builds yielded byte-identical archives. All packaged file hashes were verified after extraction. Ten tests passed under each of Python 3.10 and 3.14 with warnings treated as errors. The extracted CLI returned twelve observed fields and rejected an unlisted project with exit code 2.
- Direct MCP clients used `2025-11-25` and `2026-07-28`. Both returned the same JSON in the text and structured fields on each call. Both closed on EOF with exit code 0. The older `2025-06-18` initialization path was exercised in regression tests.
- Codex 0.166.0 discovered and invoked the packaged tool through `mcpServer/tool/call` in isolated default and July 2026 profiles. The credential-free GitHub control returned explicit unavailable remote fields while local data remained available. Both app-server processes closed without forced termination. This route issued no inference request.
- Authorization regressions established denial and argument rejection before reader construction or subprocess launch. Other regressions exercised repository-ID mismatch, deadlines, byte limits, cancellation, and failure evidence.

| Live MCP route | Operation elapsed | Git process attempts | GitHub `GET` command attempts | Result JSON bytes |
|---|---:|---:|---:|---:|
| Legacy | 1,624.7 ms | 11 | 10 | 7,837 |
| July 2026 | 1,537.5 ms | 11 | 10 | 7,837 |

Each row covers one operation from authorization through collection. Counts come from process launch attempts. Actual HTTP retries, model telemetry, provider cost and comparable roster-wide savings were unavailable. The Stage 0A timing covered broader acquisition and verification activity, including independent measurements. The live checks above establish the local implementation’s behavior in this environment. Model-driven runs against private TrackForge data would require the corresponding data authorization.

### Live repeatability

At 10:49–10:50 p.m. EST on November 26, 2026, three fresh local stdio processes each completed W1 against the same observed TrackForge state. Independent Git and GitHub reads agreed on all 12 fields in each trial. The clean checkout, remote observations and 11 Git metadata fingerprints agreed throughout.

| Trial | Collection time | Git process attempts | GitHub `GET` command attempts | Result JSON bytes |
|---|---:|---:|---:|---:|
| 1 | 1,606.4 ms | 11 | 10 | 7,837 |
| 2 | 1,475.6 ms | 11 | 10 | 7,837 |
| 3 | 1,539.8 ms | 11 | 10 | 7,837 |

The median was **1,539.8 ms**. Each server exited with code 0 after EOF. The timings cover collection inside the tool. Startup, independent verification and provider inference are outside that measurement window. A matched provider benchmark remains a separate milestone and requires approved data access or an approved redacted fixture.

Current limitations include branch and check page limits, GitHub access failures, and unavailable local change counts when inspection would require submodule worktrees or configured clean filters. The implementation exposes these limits in result dispositions rather than reporting empty findings. GitHub workflow logs remain outside the data returned by the tool.

## Stage 0C continuity

The director accepted the Stage 0C handoff with a Claude Code exception on November 26, 2026 and confirmed that work should continue. The compatibility report and packaged README record the far-future retest, which requires an eligible Claude subscription and director approval. That test remains required for a four-client technical result. Grok’s verified supervised probe evidence applies to the original fixture. The separate Stage 1 candidate has direct protocol and Codex app-server evidence.

## WPAI Constitution

The run froze v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9`. The proposed `PERF-REASON-001` amendment makes benchmark measurement boundaries explicit. The patch passed `git apply --check` on the canonical checkout. In a detached local review copy, source validation and the full 165-test suite completed with one platform skip for case-sensitive Windows paths. The proposal is staged only. Patch SHA-256 `ddeef0e04e27403c309d9b1e87c70fadfc6a55af504178183dee9b948ee23e8d`.

The SOP record covers all ten stages and fifteen Section 0 checks for this local Stage 1 delivery. It records the separate open Claude criterion and lack of remote deployment. The package is the local handoff.

Protocol and API references. [MCP legacy lifecycle](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle), [MCP July 2026 stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio), [GitHub workflow jobs](https://docs.github.com/en/rest/actions/workflow-jobs), [GitHub check runs](https://docs.github.com/en/rest/checks/runs).

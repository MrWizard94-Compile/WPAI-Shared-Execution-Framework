# Stage 1.2 synthetic W1 benchmark

Both arms use `wpai-exec` 0.1.1 from the exact Stage 1.1 ZIP. `benchmark.py` checks its SHA-256 and manifest before extracting only `wpai_exec.py` and `repo_health.py` into a disposable child directory. `server.py` imports the unchanged package, injects the fixed acquisition function, and starts its original `Stdio`. The fixture replaces the descriptions and allowlisted selector values in the benchmark catalog. The treatment keeps the production tool name, argument shape, result schema and result-handling code. The control exposes exactly one field per call. The child audit hook denies filesystem opens, subprocess creation and socket operations after setup. The fixture never queries Git or a hosted repository.

## Reproduce offline

From the repository root, run the following on the existing Windows Python installation.

```powershell
py -3.10 -B -W error work/benchmarks/stage-1.2/verify_fixture.py
py -3.14 -B -W error work/benchmarks/stage-1.2/verify_fixture.py
py -3.14 -B work/benchmarks/stage-1.2/benchmark.py score synthetic-answer.json
py -3.14 -B work/benchmarks/stage-1.2/measure.py outputs/stage-1.2/runs
```

The offline verifier exercises both arms on all three revisions, checks denial and parity, and compares all twelve field objects to the independent ground truth. These direct calls produce no agent invocation evidence.

## Reproduce an authorized agent run

Each command runs one arm in fresh disposable state. The host must already provide both the eligible subscription and the installed client. Use a new evidence filename for each attempt. Secure any retry authorization before executing another trial. The tool agent has no reason to read the package, prompt or output files directly.

```powershell
py -3.14 -B -W error work/benchmarks/stage-1.2/agent_trials.py codex treatment synthetic-codex-treatment.json
```

| Client | Isolated configuration implemented in `agent_trials.py` |
|---|---|
| Codex CLI | Fresh `CODEX_HOME`, a disposable filesystem reference to the eligible existing credentials, ChatGPT sign-in route, ephemeral context, read-only approval scope and explicit tool allowlist. Shell, apps, hooks, memory, multi-agent and web paths disabled. |
| Grok Build | Fresh `GROK_HOME` and trust map, disposable reference to existing xAI OAuth, no updates or unrelated hooks or plugins, `dontAsk` plus one exact qualified MCP permission. The published `GROK_ROUTING` string is identical across the two selected Grok arms and only specifies the native wrapper syntax. |
| Antigravity | ACP stdio, fresh app-data directory alongside the existing signed-in profile, terminal sandbox enabled, default customizations disabled, one fixture server, exact tool-token matching and approval only per call. Host terminal and filesystem callbacks are denied. |
| Gemini CLI | Separate disposition. Its eligible authentication route was unavailable. |
| Claude Code | Approved deferral. |

The evidence retains normalized tool events, independent server reply digests, result scores, measured times and exposed usage fields. Actual account credentials and ephemeral IDs are excluded. The runner verifies fixture process cleanup without publishing the Windows IDs. Agent and fixture process timing use monotonic clocks. Field equality, paired eligibility and reduction rules are in `measure.py`.

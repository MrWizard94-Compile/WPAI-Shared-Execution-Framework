# Future preflight decisions

**Decision now — NO-GO for each pinned native route.** Only a `PROVEN_ISOLATED` result can proceed to a separate proposal. Any future authorization must name the precise client, isolation mechanism, account effects, allowed tool, and session budget. Approval for a different account, development API key, or new sign-in would define a new scope.

## Codex CLI 0.166.0 · PARTIAL_ISOLATION

| Decision area | Record |
|---|---|
| Pinned identity | Windows `codex.exe` 0.166.0, release `rust-v0.166.0`, source `6ff1e1ca3b30fc8b914720681fcf5fe62e95f856`. The SHA-256 is in the matrix. `cx-home`, `cx-archive`. |
| Auth and scope | Existing ChatGPT subscription in the archive. File storage and encrypted storage are rooted at the resolved directory. Windows keyring entries retain OS logon scope. Memory storage is limited to the process, with no persistent fallback. A new process still needs an authorized source of subscription auth. `cx-file`, `cx-keyring`, `cx-secret-keyring`, `cx-ephemeral`. |
| Configuration and remaining shared state | An independent home and trusted fixture workspace can scope some preferences and files. System/cloud layers, OS-level credential access, Windows profile plugin cache, SQLite overrides and remote MCP OAuth are separate. `cx-config`, `cx-logs`, `cx-cache`, `cx-mcp-oauth`. |
| Managed policy and allowlist | Keep policy authoritative. Require evidence that the effective catalog contains just the synthetic tool, with ordinary/workspace/managed additions, app tools, plugins, lookup and external OAuth excluded as authorized. Empty tables do not erase merged entries. `cx-merge`, `cx-enforcement`, `cx-runtime-tools`. |
| Updates and workers | Check all helper and updater behavior for the archived exec route. Its app-server is in process, and its MCP server is a separate local child. No startup-update promise is inferred from TUI settings. `cx-mcp-env`, `cx-update`. |
| Account effects and next decision | Require vendor-supported evidence for an independently scoped subscription handoff with no ordinary credential reads or provider-side changes. A second sign-in or delegated-token route needs a different authorization and proof of device and refresh effects. Continue with the synthetic fixture in the meantime. `cx-device`, `cx-account-gap`. |

## Google Antigravity CLI 1.5.18 · UNKNOWN

| Decision area | Record |
|---|---|
| Pinned identity | Windows `agy.exe` 1.5.18. The matrix carries the recorded Windows installer-manifest SHA-512. Exact Windows implementation and release tag remain unresolved. `ag-build-gap`. |
| Auth and scope | The archived standard-input ACP route reported existing Google sign-in. Current documentation describes shared Windows Credential Manager usage across local surfaces, but the exact 1.5.18 lookup target, scope, fallback, persistence and renewal behavior are unknown. Gemini API-key and ADC alternatives have different auth and billing semantics. `ag-archive-route`, `ag-auth-doc`, `ag-os-scope`. |
| Configuration and remaining shared state | The old app-data and log selectors covered part of the archived ACP setup. Global preferences, workspace roots, cache and app/IDE/SDK or worker state could remain shared. A worker process does not imply another Windows logon or store. `ag-archive-state`, `ag-logs-doc`, `ag-worker-doc`, `ag-state-gap`. |
| Managed policy and allowlist | Require exact guidance for Windows managed-policy precedence and shared application/worker state. Enumerate the effective tool catalog from global, managed, workspace, default, plugin, built-in and ACP sources. Historical allow-once handling and the session-local MCP route do not prove that exclusion. `ag-archive-route`, `ag-tools-doc`, `ag-state-gap`. |
| Updates and workers | Establish whether the pinned stdio route uses separate or reused workers and whether helpers update or write outside the chosen root. Rolling per-session HTTP setup does not answer these questions. `ag-worker-doc`, `ag-state-gap`. |
| Account effects and next decision | Obtain exact Windows implementation documentation for credential namespace and refresh/writeback first. Separately approved Windows-user isolation could be evaluated only if the subscription can be used through a documented route and account/session effects are known. The present task authorizes no sign-in or new account. `ag-build-gap`. |

## Grok Build 1.0.92 · PARTIAL_ISOLATION

| Decision area | Record |
|---|---|
| Pinned identity | Windows `grok.exe` 1.0.92, build `b06756fd6256`. The binary SHA-256 is in the matrix. There is no proven correspondence to the public source mirror. `gr-mirror`. |
| Auth and scope | The archived headless route used existing xAI OAuth subscription auth with a reference to the ordinary file. Current OAuth/device/API-key options do not prove how this Windows build resolves, renews, clears or replaces its account, keyring or MCP state. `gr-archive-auth`, `gr-auth-doc`, `gr-credential-gap`. |
| Configuration and remaining shared state | Scratch `GROK_HOME`, isolated user/project config sources and scoped trust were observed within the historical checks. Background sharing, imported paths, cache/history/memory roots, policy and outside-home paths remain unresolved. `gr-archive-config`, `gr-config-gap`. |
| Managed policy and allowlist | Confirm the exact policy hierarchy and effective catalog while retaining managed pins. Prove exclusion of inherited MCP, imported agents, hooks, plugins, built-in search and non-synthetic tools. The control's extra search event keeps this gate open. `gr-archive-config`, `gr-policy-doc`, `gr-mcp-doc`. |
| Updates and workers | The historical run requested updater suppression. Exact Windows update behavior and whether it joins a shared or leader process are unproven. `gr-archive-config`, `gr-mirror`, `gr-config-gap`. |
| Account effects and next decision | Require evidence for the exact build that a provider-supported credential scope preserves ordinary sign-in, and document refresh/session replacement effects. Keep using the separate synthetic owner and relay for lifecycle work until eligible. `gr-credential-gap`. |

A separate OS user, vendor-provided account isolation, or a later in-memory backend may help with a future design. Each would require a new investigation of the exact route, normal account isolation, and provider-side registration. Stage 1.6 remains available for continued synthetic verification. The frozen Stage 1.5 proposal still caps qualification at six future cases if every route separately becomes eligible and is approved. The five-pair study stays outside that limit and remains unauthorized. [Frozen repeatability plan](../stage-1.3/repeatability-plan.json) · [Frozen qualification plan](../stage-1.5/qualification-plan.md) · [Synthetic preflight](../stage-1.6/handoff.md).

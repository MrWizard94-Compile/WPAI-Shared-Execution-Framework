# WPAI Shared Execution Framework Stage 0A

**Environment, integration and baseline readiness audit · November 26, 2026**

## A. Executive assessment

One provider-neutral Windows execution core is feasible for Grok Build, Codex, Gemini CLI and Claude Code. Start with a fixed MCP tool catalog over stdio and test the `2025-06-18` legacy handshake first. Codex CLI 0.166.0 advertises that revision in legacy mode. Defer July 2026 MCP, remote hosting and native task extensions as shared requirements until four-client tests establish a need. Each client can have its own launch profile and use the same server artifact and typed execution core.

Grok Build, Codex and Claude Code are installed. Gemini CLI was absent from the inspected installation locations. Gemini’s documentation supports the proposed transport and identifies a schema transformation the server must account for. A shared-endpoint handshake and call remain unverified across all four. The existing Codex loopback registration failed a single TCP probe.

TrackForge W1 took **33.523 seconds** from first acquisition dispatch to final check. Local and live remote branch tips matched. The local checkout had **13 unstaged modifications**. GitHub had **zero open PRs** and returned **no workflows, runs or checks**. The Desktop W1 had no attributable provider token or cost telemetry.

## B. Windows and four-agent environment

| Component | Observed version and location | Functional evidence and limits |
|---|---|---|
| Windows and shell | Windows 11 Home 26H2 x64, build **26300.10075**. PowerShell **7.6.9** from the Codex primary runtime. | CIM and PowerShell commands worked. LocalMachine execution policy RemoteSigned. CIM reports firmware virtualization disabled. |
| Hardware | Intel i7-9700, 8 cores / 8 logical CPUs. 47.88 GiB RAM, about 32.41 GiB free at inspection. C: 928.16 GiB total / 46.55 GiB free. E: 931.51 GiB / 688.65 GiB free. D: 1.25 GiB / 0.024 GiB free. | CIM point readings converted from bytes/KiB. C: is the relevant constraint for local evidence. No sustained load measurement. |
| Python and SQLite | PATH Python **3.10.11**, SQLite **3.40.1**, at `%LOCALAPPDATA%\Programs\Python\Python310`. Launcher `py -3.14` resolves **3.14.3**, SQLite **3.50.4**, at `%LOCALAPPDATA%\Python\pythoncore-3.14-64`. uv **0.10.0**. | Both interpreters imported SQLite. Installed Python MCP packages were **1.0.0** on 3.10 and **1.26.0** on 3.14. The 1.26.0 package declares `2025-11-25` as its latest revision. |
| Git and GitHub CLI | Git for Windows **2.55.0.windows.3** under Program Files\Git. GitHub CLI **2.95.0** under Program Files\GitHub CLI. | Both accessed the private TrackForge repository using existing authorized credentials. |
| Rust and Cargo | Default stable Windows x64 MSVC binaries both **1.97.1** in `%USERPROFILE%\.rustup\toolchains`. Rustup also lists named **1.85.0** and **1.97.1**. | Version probes ran against real binaries. Linker and crate resolution untested. |
| CMake and MSVC | CMake **4.4.2**. VS Community 2022 **17.14.37411.7**, MSVC **19.44.35228**. VS Community 2026 **18.11.12328.437**, MSVC **19.51.36260**. | Both x64 `cl.exe /?` probes succeeded. CMake recognizes the Ninja and VS generators. No Ninja executable resolved in PATH, the checked package locations or VS installations. TrackForge declares Ninja **1.13.2**, whose availability remains unverified. |
| Java and Gradle | Temurin JDK **21.0.10+7** under Program Files\Eclipse Adoptium. User Gradle wrapper cache has launcher JARs **8.8, 8.12, 8.14, 9.2.1, 9.5.0, 9.7.1**. | Java and javac version probes succeeded. Standalone Gradle absent from PATH. No wrapper, build or daemon launched. |
| Node and automation | Node **25.6.0**, npm **11.8.0** under Program Files\nodejs. Windows Task Scheduler service running. WSL service running. Docker CLI **29.5.3**, Windows Docker service stopped. | Node, npm and Docker CLI version probes succeeded. Docker engine and WSL distributions untested. `act`, `n8n`, `temporal` and `ollama` did not resolve in PATH. GitHub Actions REST, PowerShell, Node and Codex automations are available orchestration surfaces. No standalone WPAI workflow runtime was identified. |

Local evidence came from CIM, the Windows build registry, `Get-Command`, `vswhere`, version/help probes, configuration structure checks, and installed-file metadata. No provider API key was present in the shell environment for the four providers. Stored credentials and subscription entitlements were outside the inspection. No paid API request was made.

### Grok Build, Consumer Grok and xAI API

- `%USERPROFILE%\.grok\bin\grok.exe` reports **1.0.92** stable, build `b06756fd6256`. One Grok process was visible. `grok inspect --json` in the audit directory reported five HTTP entries, one plugin, 36 skills, three agents, zero hooks and one warning. `grok mcp list --json` reported zero entries. The source scope and connection state of the five entries and the reason for the difference remain unverified. Inspect reported `mcpManagedServersOnly=true` and `managedSettingsActive=false`. Prove the target profile admits the WPAI entry before relying on it.
- User `.grok\config.toml` exists with `cli` and `ui` sections and no observed native `mcp_servers` table. User `requirements.toml` and `managed_config.toml` were absent. Neither inspected project root had `.grok\config.toml` or `.mcp.json`. Local help shows user/project registration for stdio, Streamable HTTP and legacy SSE. xAI documents importing Claude Code MCP information alongside native config. Verify literal project `.mcp.json` import and precedence, including duplicate names and trust, with a disposable project. [Settings](https://docs.x.ai/build/settings), [Claude Code compatibility](https://docs.x.ai/build/features/skills-plugins-marketplaces).
- Local help exposes allow/deny rules, permission modes, sandbox profiles and headless JSON. xAI documents PreToolUse hooks, project hook trust, and a separate sandbox for filesystem/network access. xAI also documents limits to inheriting Claude managed bypass policy. WPAI needs independent authorization even when a host approves a call. Local service access from a Grok tool remains unverified. `grok agent stdio` is ACP for driving the agent. Headless relay and WebSocket interfaces are advertised. Neither implies an active third-party integration or an MCP client handshake. [Permissions](https://docs.x.ai/build/features/permissions), [Enterprise policy](https://docs.x.ai/build/enterprise), [Headless and ACP](https://docs.x.ai/build/cli/headless-scripting).
- Consumer Grok is a separate web/app interface. Its login and local tool entitlement were unverified. Direct xAI API access was also unverified. xAI’s official API supports caller-executed functions and remote MCP on specified API surfaces. Automatic prefix caching can include repeated tool calls and results. The Responses usage object documents input, cached input, output and reasoning counts. xAI documents cost ticks where returned. Prompt-cache routing and eviction affect hits. API capability establishes neither availability nor metering in the consumer app or Build subscription. [Consumer FAQ](https://docs.x.ai/grok/faq), [Function calling](https://docs.x.ai/developers/tools/function-calling), [Remote MCP](https://docs.x.ai/developers/tools/remote-mcp), [Prompt cache usage](https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing), [API usage best practices](https://docs.x.ai/developers/model-capabilities/text/best-practices).

### Codex CLI, Desktop and IDE

- PATH Codex at `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin` reports **0.166.0**. The installed Desktop package **26.1120.6357.0** bundles a separate **0.171.0-alpha.13.2** binary. The `openai.chatgpt` VS Code extension **26.1111.21308** was found on disk. IDE runtime activation and its binary choice remain unverified.
- `codex mcp add NAME -- COMMAND ...` registers stdio. `--url` registers Streamable HTTP. The user `.codex\config.toml` had three MCP entries and `codex mcp list --json` returned five effective entries, with three enabled stdio, one disabled stdio and one enabled loopback HTTP. The loopback TCP probe failed from the shell within 1.5 seconds. This chat also exposes app/plugin tools, including a Minecraft MCP namespace. Those tools belong to the Desktop session. No local `.codex\config.toml` existed in either inspected project and the checked user and ProgramData requirements files were absent.
- Config supports `enabled_tools`, `disabled_tools` and tool approval modes. CLI help lists `read-only`, `workspace-write` and `danger-full-access`. Interactive help advertises `on-request` and `never` approvals. The audit chat had `danger-full-access` and `never` and constrained the commands to reads. User config selects `elevated` as its Windows sandbox implementation. Current docs also describe MXC and unelevated, whose runtime availability was not established here. `codex exec` advertises JSONL, ephemeral runs, sandbox selection and final-output schema. Headless approval can fail closed and must be tested separately. [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox), [Approvals](https://learn.chatgpt.com/docs/agent-approvals-security), [Noninteractive mode](https://learn.chatgpt.com/docs/non-interactive-mode).
- The pinned **0.166.0** source prefers `2025-06-18` in legacy mode and supports eligible `2026-07-28` paths. The local listing showed `mcp_2026_07_28` and `mcp_tool_list_changed` under development and false. The pin distinguishes stdio discovery and the launch variable `CODEX_MCP_PROTOCOL_VERSION` under applicable policy. The separate `codex_apps_mcp_2026_07_28` flag is for hosted Apps. Desktop alpha and IDE wire behavior still need samples. [Pinned protocol modes](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/rmcp-client/src/protocol_mode.rs#L8-L49), [Pinned features](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/features/src/lib.rs#L1640-L1663), [Pinned app-server notes](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/app-server/README.md#L157-L166).

### Gemini CLI

- Gemini was absent from PATH, the resolved global npm package root, and the inspected npm shim, user bin and app directory candidates. The standard `.gemini` user directory and ProgramData system/default settings files were absent. The checked VS Code and Cursor extension locations contained no matching Gemini Code Assist entry. A portable installation elsewhere remains possible.
- Official `mcpServers` configuration uses `%USERPROFILE%\.gemini\settings.json` and project `.gemini\settings.json`. Use `command` for stdio, `httpUrl` for Streamable HTTP and `url` for legacy SSE. Server and tool filters apply. `excludeTools` takes priority over `includeTools`. Project trust and policy differ from per-server `trust`, which bypasses tool confirmation. Google login, API-key and Vertex authentication have distinct accounting. [Configuration](https://geminicli.com/docs/reference/configuration/), [MCP servers](https://geminicli.com/docs/tools/mcp-server/), [Authentication](https://geminicli.com/docs/get-started/authentication/).
- Gemini documents removing `$schema` and `additionalProperties` from model-facing tool schemas, sanitizing names and prefixing conflicts. It documents structured tool responses and rich MCP content. Exact retention of `structuredContent` and enforcement of `outputSchema` in the selected client remain unverified. Server-side validation is required. [Gemini schema compatibility](https://geminicli.com/docs/tools/mcp-server/).

### Claude Code, Desktop and IDE

- Native `%USERPROFILE%\.local\bin\claude.exe` reports **2.1.243**. Desktop MSIX **6.28899.6.0** and VS Code extension files **2.1.327** and **2.1.175** were present. Desktop `%APPDATA%\Claude\claude_desktop_config.json` declares two stdio entries. User Code settings have a permissions section. `.claude.json` had no top-level MCP entries or scoped MCP entries for the inspected project roots. Both lacked `.mcp.json` and Claude Code project settings. Checked managed files under Program Files\ClaudeCode and HKLM/HKCU ClaudeCode policy keys were absent. Account-delivered policy and server health were unverified.
- Installed options show stdio/HTTP/SSE transports, user/local/project scope, `--mcp-config` and `--strict-mcp-config`. Shared project MCP uses `.mcp.json`. User/local MCP uses `.claude.json`. Claude Code supports project approval, allow/ask/deny rules, managed controls, trust and PreToolUse hooks. The installed CLI restricts Desktop auto-import to Mac/WSL. Native Windows stdio should use a vetted explicit executable and verify quoting and clean shutdown. `claude mcp list` was excluded because installed help says it health-checks approved servers. [MCP registration](https://code.claude.com/docs/en/mcp), [Settings](https://code.claude.com/docs/en/settings), [Permissions](https://code.claude.com/docs/en/permissions).
- The documented v2 runtime supports July 2026 MCP. **2.1.243** meets the **2.1.232+** condition for sessions fetching feature flags and is below the **2.1.274+** default for sessions without those flags. Negotiation can be set to legacy or fall back. The actual runtime was unverified. Current docs describe a **10,000-token** warning, a **25,000-token** default MCP output cap via `MAX_MCP_OUTPUT_TOKENS` and eligible large text output persisted to a file after **50,000 characters**. Verify these on the scoped build before depending on them. [Claude MCP runtimes and limits](https://code.claude.com/docs/en/mcp).

## C. Four-agent MCP compatibility matrix

**CONFIRMED** means directly observed for the named action. **DOCUMENTED** means vendor docs or pinned client source support it. **UNVERIFIED** means insufficient evidence. **UNSUPPORTED** means a known limitation of the named surface. Help confirms the presence of a switch. Wire behavior requires a negotiation or tool call.

| Capability | Grok Build 1.0.92 | Codex CLI 0.166.0 | Gemini CLI | Claude Code 2.1.243 |
|---|---|---|---|---|
| Registration surface | **CONFIRMED** help, inspect, list | **CONFIRMED** help and list | **DOCUMENTED** settings/CLI. Binary absent in checked locations. | **CONFIRMED** help and scopes |
| Client-launched stdio | **DOCUMENTED**. Managed policy needs validation. | **DOCUMENTED**. Three enabled entries observed. | **DOCUMENTED** via `command`. | **DOCUMENTED** with trust/Windows path checks. |
| Streamable HTTP | **DOCUMENTED**. Five entries in inspect, reachability unverified. | **DOCUMENTED**. **CONFIRMED** negative shell TCP probe to one configured endpoint. | **DOCUMENTED** via `httpUrl`. | **DOCUMENTED** via `--transport http`. |
| Standalone legacy HTTP+SSE | **DOCUMENTED**. | **UNSUPPORTED** in documented standalone registration. Streamable HTTP can still return SSE. | **DOCUMENTED** via `url`. | **DOCUMENTED**, deprecated by vendor. |
| Legacy `initialize` and exact version | **UNVERIFIED** range. | **DOCUMENTED** `2025-06-18` preference in pinned source. | **UNVERIFIED** for target Windows build. | **DOCUMENTED** legacy runtime/fallback. Session version **UNVERIFIED**. |
| July 2026 modern negotiation | **UNVERIFIED**. | **DOCUMENTED** eligible opt-in. Default-off listing **CONFIRMED**. Live wire **UNVERIFIED**. | **UNVERIFIED**. | **DOCUMENTED** with v2 and applicable flags. Local runtime **UNVERIFIED**. |
| Tool discovery and refresh | **DOCUMENTED** discovery. Refresh **UNVERIFIED**. | **DOCUMENTED** discovery. Experimental change notifications off locally. Refresh **UNVERIFIED**. | **DOCUMENTED** discovery. Refresh **UNVERIFIED**. | **DOCUMENTED** dynamic updates, limited by runtime/stream. |
| Common input schema | **DOCUMENTED** tool interface. Shared schema **UNVERIFIED**. | **DOCUMENTED** tool interface. Shared schema **UNVERIFIED**. | **DOCUMENTED** transformations. Model-facing preservation of `$schema` and `additionalProperties` **UNSUPPORTED**. | **DOCUMENTED** tool interface. Shared schema **UNVERIFIED**. |
| `outputSchema`, `structuredContent` and mirrored JSON text | **UNVERIFIED** end-to-end. | **UNVERIFIED**. Final-response schema flag is separate. | **DOCUMENTED** structured tool responses. Field retention and output validation **UNVERIFIED**. | **UNVERIFIED**. Final-response schema flag is separate. |
| Catalog TTL and scope semantics | **UNVERIFIED**. | **UNVERIFIED**. Pinned source has a catalog cache. | **UNVERIFIED**. | **UNVERIFIED**, including v2. |
| Tool filtering, confirmation and trust | **DOCUMENTED** rules/hooks. Effective Grok policy unresolved. | **DOCUMENTED** filters/approval modes. | **DOCUMENTED** include/exclude, trust and policy. | **DOCUMENTED** rules, hooks and approval. |
| Remote transport auth | **DOCUMENTED** headers. OAuth for proposed profile **UNVERIFIED**. | **DOCUMENTED** bearer env and OAuth. | **DOCUMENTED** headers and OAuth. | **DOCUMENTED** OAuth, headers and scopes. |
| July 2026 Tasks extension | **UNVERIFIED**. | **UNVERIFIED** for third-party MCP. | **UNVERIFIED**. | **DOCUMENTED** conditional per-request opt-in on v2. |
| Cursor and opaque evidence handle | **UNVERIFIED**. | **UNVERIFIED**. | **UNVERIFIED**. | **UNVERIFIED**. |

The matrix uses Section B sources. No new endpoint call was made. Registration, CLI feature listing, and TCP reachability establish distinct claims. A July 2026-only server is incompatible with a legacy-only client unless it offers a legacy path.

### Protocol floor and SDK choices

MCP stdio uses client-launched, newline-delimited UTF-8 JSON-RPC. Keep stdout reserved for protocol messages. Use stderr for bounded sanitized diagnostics. Streamable HTTP uses a single endpoint with JSON or SSE responses. July 2026 replaces the connection handshake with `server/discover` and stateless request metadata, formalizes extensions, adds ordered cacheable lists with TTL and scope, and hardens HTTP authorization. Earlier sessions use `initialize` and `notifications/initialized`. A mixed deployment must support both eras on the chosen binding. Keep the first catalog small and fixed, with deterministic order and reconnect discovery. Treat catalog caching, provider prompt caching and evidence caching as independent. [July 2026 specification](https://modelcontextprotocol.io/specification/2026-07-28), [Legacy transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [July 2026 release](https://blog.modelcontextprotocol.io/posts/2026-07-28/).

Use object-shaped input with simple scalar properties and required fields. Validate unknown fields, types and bounds in the core. Return an object in `structuredContent` when supported and the equivalent bounded JSON in text. Distinguish tool result validation from model final-reply formatting. Test MCP discovery cursors separately from WPAI evidence cursors. If a real workload needs long jobs, use opaque operation IDs and bounded status/result/cancel calls. Native Tasks need extension capability on the relevant request and should be optional. [MCP tool schemas and results](https://modelcontextprotocol.io/specification/2026-07-28/server/tools), [Tasks extension](https://tasks.extensions.modelcontextprotocol.io/seps/2663-tasks-extension), [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization).

Python MCP **1.26.0** is the installed legacy candidate. Verify its fallback and `2025-06-18` interoperability before pinning it. Python SDK v2 needs Python **3.11+** and documents one server for both eras. It has a different API and does not implement the July 2026 Tasks extension. TypeScript SDK v2 provides a dual-era path. Rust `rmcp` is a viable option and used by the pinned Codex release. Choose one SDK after the conformance run. [Python install](https://py.sdk.modelcontextprotocol.io/get-started/installation/), [Python v2](https://py.sdk.modelcontextprotocol.io/whats-new/), [TypeScript SDK](https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28), [Rust SDK](https://github.com/modelcontextprotocol/rust-sdk).


## D. Constitution alignment

Accepted canonical `main` resolved to **`0adf5ecee5f7f96ce3749944dc097a003731a6e9`**, version **6.24.0**. The source checker matched all 23 manifest files to that commit, and the loader version matched. `validate-source.py` passed. The exact-SHA source CI run succeeded. The always-load set, relevant laws, registry and local WPAI/TrackForge instructions were inspected. TrackForge declares a proprietary local-first DAW scope. Its build, AI and runtime behavior were outside W1. [Frozen source](https://github.com/MrWizard94-Compile/Agents-Constitution/commit/0adf5ecee5f7f96ce3749944dc097a003731a6e9), [Exact-SHA CI](https://github.com/MrWizard94-Compile/Agents-Constitution/actions/runs/45404019842).

| Proposed requirement in the objective | Canonical coverage |
|---|---|
| Compact evidence and fewer redundant calls | `COST-TOKEN-001` in `law/SPECIALIST.md`. `CONST-QUALITY-001` in `AGENTS.md` protects applicable verification. |
| Cache minimum safe facts and revalidate after drift | `COST-CACHE-001` in `law/SPECIALIST.md` covers both. It excludes raw private data and secrets from the working cache. |
| Reproducible baseline, equivalent windows, real token/time/resource limits | `PERF-REASON-001` and `PERF-BUDGET-001` in `law/ENGINEERING.md`. `RND-DOC-001` and `ENG-REPRO-001` support reproducibility. |
| Typed, versioned contracts, bounded payloads, retry and failure semantics | `NET-PROTO-001` and `NET-DOC-001` in `law/SPECIALIST.md`. `SEC-INPUT-001` governs untrusted inputs and `ENG-FW-001` requires actual consumer evidence. |
| Independent authorization, read/write separation and approved external actions | `SEC-PRIV-001` and `SEC-AUTHZ-001` in `law/SECURITY.md`, with `NET-AUTH-001` and `CONST-AUTH-001`. |
| Safe audit history, compact evidence and root-cause failure reports | `OBS-LOG-001`, `OBS-FAIL-001`, `OBS-PRIV-001` and `SEC-SECRET-001` in `law/SECURITY.md`. |
| Authorized fallback, clean repository state and reviewable handoff | `CONST-RESOURCEFUL-001` in `AGENTS.md`, `SOP-EXEC-001` in `SOP.md` and `VCS-CLEAN-001` / `OPS-DEL-001` in `law/OPERATIONS.md`. |

**Disposition of `COST-EXEC-001`.** There is no active ID in the frozen registry and the objective supplies requirements rather than separate draft law. Use a **project verification profile** mapped to existing rules. One gap exposed by W1 is ambiguity when benchmark authors report wrapper calls, actual operations, provider usage and elapsed time without distinct boundaries. If a cross-project mandate is later desired, its precise home is **`PERF-REASON-001` in `law/ENGINEERING.md`**. Require independent definitions, units, provenance and observation windows for these measurements. A reviewer can falsify compliance with a run whose wrapper count stays constant while subprocess/API counts vary, or whose provider telemetry is absent. `COST-TOKEN-001` still owns compact evidence. The inspection-only scope authorized a recommendation. No amendment, branch, commit or distribution occurred. [Rule registry](https://github.com/MrWizard94-Compile/Agents-Constitution/blob/0adf5ecee5f7f96ce3749944dc097a003731a6e9/governance/RULE-REGISTRY.md), [Performance rule](https://github.com/MrWizard94-Compile/Agents-Constitution/blob/0adf5ecee5f7f96ce3749944dc097a003731a6e9/law/ENGINEERING.md#L245), [Evolution](https://github.com/MrWizard94-Compile/Agents-Constitution/blob/0adf5ecee5f7f96ce3749944dc097a003731a6e9/governance/EVOLUTION.md).

## E. W1 TrackForge repository health baseline

**Acquisition window** · November 26, 2026, **14:04:56.244–14:05:29.767 EST**. Ordinary Codex Desktop tool calls used PowerShell, Git and GitHub CLI.

| # | W1 field | Result |
|---|---|---|
| 1 | Canonical identity | Private `MrWizard94-Compile/TrackForge`, GitHub repository ID **1351477573**, default `main`. Local fetch/push origin matched the canonical target. |
| 2 | Local branch and HEAD | `C:\WPAI\Software\TrackForge`, active `staging`, `bba3e4b24d28b0cb77572115c8fe0357dc66da28`. Non-shallow repository. |
| 3 | Accepted remote main | `bba3e4b24d28b0cb77572115c8fe0357dc66da28`, independently via GitHub ref API and `git ls-remote --heads`. |
| 4 | Working tree | Dirty. Both porcelain status and diff found 13 tracked modifications. Git index SHA-256 matched before and after initial status. |
| 5 | Change counts | **0 staged, 13 unstaged tracked, 0 untracked, 0 unmerged**. Root 2, `docs` 4, `source` 5, `tools` 2. Ignored files outside this measurement. |
| 6 | Branch inventory | Local `main` and `staging`. Cached `origin/main` and `origin/staging` plus symbolic `origin/HEAD → origin/main`. Live heads `main` and `staging` only. All branch tips were the same HEAD. No stale tracking ref identified in this snapshot. |
| 7 | Divergence | Local `main` and active local `staging` each **0 ahead / 0 behind** live `main` by equal SHA. Local `rev-list` likewise returned 0 / 0 against cached `origin/main`. |
| 8 | Latest commits | Five newest local and live main hashes and subjects matched. See table below. |
| 9 | Open PRs | **0**. GitHub returned an empty open-PR result, so destinations were inapplicable. |
| 10 | GitHub Actions | **0** workflows and runs repository-wide and on both branches. Exact-SHA **0** check runs and legacy commit statuses. Combined status `pending` had an empty statuses list. The local tree at the exact remote SHA had no `.github/workflows` entries. No applicable CI result is recorded. |
| 11 | Failed check causes | No failed check/job surfaced, so no remote failure cause applied. A separate local `git diff` warning came from LF in the index, CRLF on disk and `text eol=lf` on `tools/tracktion-probe/TrackForgeNativeMidiDeviceTests.cpp`. The file was preserved. |
| 12 | Discrepancies | Commit/ref tips agree. The local working copy has changes beyond the common commit. The remote provides no CI evidence for build, runtime or DAW acceptance at this SHA. |

| Commit | Commit time EST | Summary |
|---|---|---|
| `bba3e4b24d28` | 11:28:35 | Dated remaining full-product status statements in MANIFEST |
| `df23dbe46f10` | 11:24:51 | Qualified the remaining October adoption statements in MANIFEST |
| `df6ee3132eba` | 11:15:56 | Documented the Native desktop as the current delivery |
| `9b238a4692b6` | 09:34:49 | Recorded consolidation acceptance and the Constitution pointer |
| `c42a9fa98fc1` | 08:57:34 | Added a sample-accurate recording count-in |

[TrackForge commit](https://github.com/MrWizard94-Compile/TrackForge/commit/bba3e4b24d28b0cb77572115c8fe0357dc66da28), [Pull requests](https://github.com/MrWizard94-Compile/TrackForge/pulls), [GitHub Actions](https://github.com/MrWizard94-Compile/TrackForge/actions).

| Metric | Result | Method |
|---|---:|---|
| Visible Codex tool calls | **3** | Direct count of outer acquisition calls. |
| Shell tool invocations | **6** | Direct count of PowerShell invocations. Several ran in parallel. |
| Explicit external command invocations | **30** | Derived count of 20 Git and 10 GitHub CLI commands. Two PowerShell index hash operations also ran. Credential helpers and other descendant processes were unobserved. |
| GitHub operations | **10 REST GET operations**, **1 Git remote ref-list operation** | Derived from invoked commands. Wire requests, redirects, retries and Git negotiation were unobserved. |
| Acquisition elapsed time | **33.523 s** | Direct outer timestamp difference. Includes between-call reasoning time and excludes preparatory policy reads and drafting. Full prompt-to-report latency is unavailable for W1 within the combined audit. |
| Sum of shell tool durations | **10.095 s** | Derived from the six tool-reported durations. Parallel work is included in the sum. |
| Input, output, reasoning and cached tokens | **Unavailable** | No W1-scoped provider telemetry in this Codex Desktop context. |
| Provider cost and subscription usage | **Unavailable** | No W1 charge or quota delta exposed. No separate paid API calls. |
| Coverage | **12/12 fields dispositioned** | Derived by mapping W1 fields to evidence or a reason the field did not apply. CI failure diagnosis was inapplicable here. |
| Accuracy | **Cross-checked, without an overall percentage** | Live main via Git and REST, dirty counts via status and diff, recent commits via Git and REST, CI absence via several endpoint families and the exact tree. No dirty-file content fingerprint was taken during this run. |

The six observations were local snapshot, remote repository/refs metadata, live remote ref listing, CI follow-up, working-tree diff, and exact tree/line-ending confirmation. Their tool-reported durations in that order were 1.453, 2.969, 1.958, 2.597, 0.568 and 0.549 seconds. The audit retained summaries and exact identifiers without collecting full project files or job logs.

## F. Telemetry and four-agent benchmark replay

| Metric | Codex | Grok Build | Gemini CLI | Claude Code |
|---|---|---|---|---|
| W1 sessions executed | One Desktop acquisition above | Zero | Zero | Zero |
| Model inference cycles | Desktop did not expose them. Completed turns and tool items may each aggregate provider work. | Streaming event count is observable. Internal cycles not exposed. | Documented headless latency and stats. Internal cycles unverified. | Streaming events observable. Internal cycles unverified. |
| Tool calls and operations | Measured for Desktop W1. CLI JSONL and app-server carry tool item events. | Documented JSON streaming and ACP events. | Documented `stream-json` tool events. | Documented `stream-json` events. |
| Subprocesses, API operations and latency | Count at the execution boundary with a monotonic timer, process starts and request IDs or explicit operations. | Same instrumentation | Same instrumentation | Same instrumentation |
| Input, output, reasoning and cached tokens | `codex exec --json` documents `turn.completed.usage` for all four. App-server reports per-thread usage. Desktop W1 unavailable. | Installed `grok usage SESSION_ID [TURN]` advertises session token/cost usage. Exact fields unverified. xAI Responses documents cached and reasoning fields. | Headless `stats` documents usage and API latency. Capture cached and thoughts fields when emitted. | Headless JSON exposes usage, cache fields and model usage where supplied. A consistently separate reasoning count unverified. |
| Subscription quota and API billing | App-server account rate limits documented. W1 delta or bill unavailable. | `grok usage` advertises plan usage via the background service. Actual API billing is separate. | Google login quota, Gemini API and Vertex each use their own route. | `total_cost_usd` in headless output is a client-side estimate. Subscription quota and actual billed usage are separate. |

Record public counters and report absent fields explicitly. Account-level quota is usable only with an attributable trial window. For an approved API trial, capture provider usage and invoices by surface. Count provider requests at an authorized boundary if supported and label that count as requests. Keep hidden model cycles unavailable. [Codex JSONL](https://learn.chatgpt.com/docs/non-interactive-mode), [Codex App Server](https://learn.chatgpt.com/docs/app-server), [Grok headless](https://docs.x.ai/build/cli/headless-scripting), [Gemini headless](https://geminicli.com/docs/cli/headless/), [Gemini caching](https://geminicli.com/docs/cli/token-caching/), [Claude headless](https://code.claude.com/docs/en/headless), [Claude monitoring](https://code.claude.com/docs/en/monitoring-usage).

### Matched W1 procedure

1. **Hold the workload fixed.** `W1-objective.txt` preserves the exact delivered Section 6, including its escaping and line endings. Its SHA-256 is `b7a8a6f0034f9456100ff8311f98873deec95e4c851d68259ddc0bf7b1aebbf2`. The updated attachment’s Section 6 exactly matched the original. Give every client the same objective and twelve fields in the order in Section E. A field must contain a value or explicit unknown reason plus source, target and timestamp. Score the separate provider metrics without exposing another agent’s answers.
2. **Hold repository state fixed.** Before the cohort and after each trial, record canonical repository ID, active branch, HEAD, live branch refs, porcelain results and index digest. For strict equivalence, record a private aggregate fingerprint of the bounded set of dirty paths. Pin independently the relevant remote PR, workflow, recent run and check observations. Mark a changed cohort unmatched. Use the same separately authorized redacted frozen fixture for all providers if live equivalence is impracticable. A future live repeat cannot recreate this run’s exact dirty bytes from the scorecard alone.
3. **Keep scope equivalent.** Use read-only Git and the same approved GitHub read scope. Allow only bounded repository metadata to enter provider context. Verify the organizational authorization and subscription route before sending private metadata to a different provider. If a client needs broader permissions, an API purchase, a hosted relay or unrelated connectors, leave that trial blocked or use the common redacted fixture. Record any unavoidable profile differences.
4. **Build the read-only oracle.** Set `GIT_OPTIONAL_LOCKS=0`, disable external fsmonitor for status, and use `rev-parse`, `symbolic-ref`, `status --porcelain=v1 --untracked-files=all`, `diff --name-status --no-renames --no-ext-diff --no-textconv`, `for-each-ref`, `ls-remote --heads`, `rev-list --left-right --count` and `log -5`. Check live GitHub routes below. Cap pages and record truncation. If tips differ, compare remotely where GitHub resolves both SHAs or use already-present objects locally. If failed checks exist, obtain job and step metadata plus a bounded redacted causal excerpt. An empty visible result and an inaccessible API response have distinct dispositions.
5. **Measure by provider.** Time both prompt-to-validated-result and acquisition with a monotonic clock. Record client build, model, effort, access route, profile, transport, resource snapshot and trial ID. Once authorized, run at least three baseline and three candidate trials per provider, with fixed provider/model/effort within each comparison. Alternate order where practical and keep fresh sessions separate from warmed sessions. Report individual results and medians. Require **12/12 field dispositions**, agreement with the oracle on observable values, zero unauthorized actions and zero secret disclosures before comparing savings.

| Oracle family | GET suffixes under `repos/MrWizard94-Compile/TrackForge` |
|---|---|
| Repository and refs | Repo root, `/git/ref/heads/main`, `/commits?sha=main&per_page=5` |
| Open PRs | `/pulls?state=open&sort=updated&direction=desc&per_page=100` |
| Actions | `/actions/workflows?per_page=50`, `/actions/runs?branch=main&per_page=25`, `/actions/runs?branch=staging&per_page=8`, `/actions/runs?per_page=12` |
| Checks | `/commits/{sha}/check-runs?filter=latest&per_page=50` and `/commits/{sha}/status?per_page=50`. When relevant, add bounded jobs, annotations and causal evidence. |

| Future launcher | Capture |
|---|---|
| Grok | `grok -p … --output-format streaming-json` with approved scoped tools. Verify update suppression and permissions on the installed build. Read `grok usage SESSION_ID [TURN]` when the supported interface records the run. |
| Codex | `codex exec --json --ephemeral -s read-only` with explicit workdir and an approved network path or local oracle. Parse `turn.completed` usage. This headless cohort is distinct from Desktop W1. |
| Gemini | `gemini -p … --output-format stream-json` after authorized installation and authentication. Scope tool policy and save final stats counters. |
| Claude | `claude -p --output-format stream-json --verbose` with an approved profile and optional strict MCP registration. Keep cost estimates distinct from a bill. |


## G. Shared execution and adapter architecture

| Layer | First working version | Defer |
|---|---|---|
| Agent boundary | Four equally supported client launch profiles over one MCP stdio artifact. Fixed tool names and argument/result contracts. Add a descriptor or response adapter only for a demonstrated client incompatibility. | Remote gateway, cloud relay, vendor API wrappers and separate orchestration implementations. |
| Execution core | One bounded, versioned W1 operation. Use explicit argument vectors, approved repo IDs, exact paths, deterministic sequencing and bounded read-only Git/GitHub requests. Report empty, unavailable, failed, stale and truncated distinctly. | Arbitrary shell or filesystem tools. Expand to PowerShell, Python, Cargo/Rust, CMake/MSVC and Gradle/JDK through typed operations once their evidence and write policies are defined. |
| Authorization | WPAI owns the decision. Use an approved launch profile and independent OS/process constraints. Resolve and validate target ownership, argument bounds and Windows reparse points. Deny writes at dispatch and executor boundaries. Human approval for any future write must bind the exact operation, target, parameters and state. | Shared cross-machine identities and unattended write permissions. Any later HTTP needs vetted scoped identity, per-request authorization, loopback or approved address, origin checks, timeouts and redacted logs. |
| State and evidence | Compact results, attempt/run ID, stable source identifiers, timestamps, partial status and primary cause. Add bounded protected history and evidence paging when needed. Bind opaque handles/cursors to caller, operation and snapshot. | Raw log archive, generalized checkpoint store, background workers and distributed state. |
| Runtime and persistence | Python fits I/O-bound orchestration and validation. Pin an interpreter and SDK after conformance. SQLite is sensible when concurrent reads, persistent comparison, retained evidence or transactional history justify it. Keep it local with ACLs, one write policy and bounded retention. | Rust rewrite until packaging or profiling offers a concrete benefit. Docker/WSL, Windows service, network exposure and external database are unnecessary for W1. |

The same core owns validation and outputs for every client. Gemini may need a thin descriptor projection if a property is dropped. A client that loses structured data can read the shared JSON text if testing confirms it. If a client requires July 2026 semantics while peers require legacy, use dual-era transport in the same host. A client that demonstrably cannot consume MCP could use a thin function-calling bridge after separate authority and cost review. Keep all workflow, authorization and evidence logic in the provider-neutral core.

## H. Risk register

| Risk | Trigger and response | Priority |
|---|---|---|
| Protocol and feature-flag drift | Build change moves handshake, refresh or task behavior. Pin and record negotiated revision for each supported surface. Retest on upgrades. | High |
| Schema and result loss | Schema conversion removes restrictions or the host drops fields or persists excess text. Enforce validation in the core and test wire, host and model-visible fields. Keep JSON fallback small. | High |
| Privilege escalation by configuration | Broad client approvals, crafted arguments, untrusted project settings or Windows junctions bypass scope. Validate exact actions and containment independently, use a least-privilege process, and test denials before subprocess creation. | High |
| Private data and untrusted tool output | Repository text, logs or environment values reach the model. Capture minimal metadata, redact locally and keep repository strings inert. Use synthetic fixtures before private use authorization. | High |
| Missing tools or unavailable profiles | Gemini absent, Codex loopback unreachable, Grok policy unclear, or Windows launcher fails. Test vetted absolute executables using isolated profiles and one legacy path. | High |
| Invalid benchmark comparison | Live repo, model, profile or cache state changes. Require oracle snapshots and recorded trial invalidation. Track cost and quota by route. | High |
| Resource and evidence growth | Startup, subprocess fan-out, retries or logs dominate the savings. Measure cold startup and aggregate process use. Cap output, attempts, evidence size and history. | Medium |
| Adapter maintenance | Client-specific behavior spreads into execution. Add an adapter only with a reproducible conformance failure. Keep one operation contract and repeat the four-client acceptance suite. | Medium |

## I. Stage 0 exit assessment

The inspection accounts for all four ecosystems and establishes a credible common design. Production implementation readiness depends on the following evidence.

- Record actual Gemini CLI availability and an authorized local profile. Confirm each provider’s entitlement and permitted data boundary. Reconcile Grok’s managed-only and inventory observations in the target profile. Confirm that the chosen transport works independently of the failed existing Codex endpoint.
- Record actual protocol, discovery, refresh, schema transformations, result handling, paging and error behavior on four clients. Confirm Claude runtime selection and Codex effective features. Test tool visibility and confirmation separately from server authorization. Evidence handles must fail securely across callers.
- Decide from W1 timings whether portable long-running jobs are necessary. If needed, test status, cancel, expired IDs and process cleanup. Keep native Tasks and Streamable HTTP optional until a real requirement exists.
- Run equivalent Grok, Gemini and Claude baselines and a separate Codex CLI baseline if headless use is the target. Validate public telemetry and compare equivalent scopes and states. Numeric token, cost and latency savings remain unmeasured.
- Establish failure-diagnosis coverage with a controlled known-failure fixture. TrackForge W1 had no failed CI result to diagnose. The fixture should also differentiate inaccessible evidence from zero findings.

## J. Recommended next goal

**Stage 0B · Prove one Windows-local MCP interface across Grok, Codex, Gemini and Claude.** Authorize a disposable synthetic fixture, the exact Gemini installation or approved alternate environment, and the intended subscription and data scopes. Keep production TrackForge, existing agent user configuration and the canonical Constitution outside the fixture’s write scope. Do the work in this order.

1. **Exercise four actual clients.** Pin each build and launch profile. Resolve Grok policy, Claude runtime and Codex feature state. Capture a successful negotiation on **4/4** clients using the same stdio artifact, with a working legacy path and no network listener. Record any optional modern pass separately.
2. **Prove one versioned contract.** Verify discovery, successful bounded call, exact argument values, output parity where both result projections are available, a second evidence page, invalid argument, expired cursor and rediscovery. Require identical report values and equivalent error categories on **4/4**.
3. **Prove enforcement.** Deny the wrong operation, target, path and caller’s handle. Require **zero** target subprocesses on denied operations and **zero** secret fields. Exercise headless approval refusal and a bounded timeout/cancel case with no lingering process.
4. **Benchmark W1.** After fixture and data authorization, run the matched cohorts in Section F. Require **12/12** observable field dispositions at equal oracle accuracy. Require provenance for every operation and timing metric. Capture provider telemetry where exposed and mark unavailable fields explicitly. Report individual results and medians before making a savings claim.
5. **Decide on Stage 1.** Record the supported transport and approved policy per provider, any adapter and the failure that requires it, the execution/resource budgets and disposition of each open item. Advance only after client compatibility and server-side authorization pass.

### Delivery audit

The report and exact W1 brief are the delivered files. The frozen Constitution revision and W1 observations were checked through independent source routes.

The addendum extended the agent assessment. The W1 definition itself was byte-identical across both attachments. The reported elapsed interval covers acquisition only.

Compatibility classifications distinguish runtime observation, documentation and unknowns. No test/build acceptance or cost savings are inferred.

The Constitution evolution obligation remains unstarted under the inspection-only scope. The report supplies an analytical placement recommendation. No apply-ready amendment was staged.


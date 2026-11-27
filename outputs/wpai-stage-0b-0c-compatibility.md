# WPAI Shared Execution Framework compatibility report

**Stages 0B and 0C · November 26, 2026**

Grok Build completed all seven synthetic calls using the unchanged Stage 0B server. A disposable process supervisor also verified graceful shutdown after all seven calls. Codex and Antigravity already had invocation evidence. **The director accepted the Stage 0C handoff with a Claude Code exception and approved proceeding to Stage 1. Three clients have verified invocation. Claude’s model-level verification remains deferred.**

## Accepted artifact

The archive and evidence digests in this section describe the original test artifacts. The published archive keeps the exact probe and launcher and uses a new manifest for the local account name substitutions in retained records.

| Item | Verified identity |
|---|---|
| Server and contract | Build **0.1.1**, `wpai.probe.v1` |
| Server SHA-256 | `d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770` |
| Launcher SHA-256 | `766a332abdd72e8233267796e2961f8b1cbc2fa9d875c656891f76bcdff32683` |
| Original Stage 0B archive SHA-256 | `b59081f4feab80c7a0c4eee1f582b0108c3815dec7c4a3a22fddcde2a56a3439` |
| Stage 0C Grok evidence SHA-256 | `a62b4164f1263027b9bc3b40be0a81a7b9b7c6a422409b07847450511876cd85` |
| Grok ACP and headless shutdown evidence SHA-256 | `447cec0e9ff12bf328e42ef8a9c9acf330cdcce0b657bf718812f979e11cae95` |
| Grok supervised invocation and shutdown evidence SHA-256 | `624c8bd589dfecc11ffc8d599c75ea164283f277dc0e89ab3a12f58dd65029a0` |

The Stage 0B archive passed CRC and all manifest checks. The server, launcher and replay sources in the existing disposable directory matched the archive byte for byte. Server and launcher hashes matched again after testing. Codex and Antigravity were compared using their retained evidence.

## Updated four-agent matrix

| Requirement | Grok Build 1.0.92 | Codex CLI 0.166.0 | Antigravity CLI 1.5.18 | Claude Code 2.1.243 |
|---|---|---|---|---|
| Registration | Confirmed in Stage 0C. Only the local probe registered for this test. | Confirmed in Stage 0B via local app-server. | Confirmed in Stage 0B via local ACP. | Confirmed in Stage 0B via isolated user-scope health check. |
| Discovery | Five tools listed by the headless client. | Five tools listed in both tested modes. | Five tools listed by the signed-in CLI. | Five tools listed in both tested modes. |
| Negotiation | `2025-11-25` legacy in the model run. | `2025-06-18` legacy and opt-in `2026-07-28`. | `2026-07-28` in signed-in run. | `2025-11-25` and opt-in `2026-07-28` for discovery only. |
| Exact echo | Confirmed in Grok’s MCP result and independent server trace. | Confirmed via direct MCP RPC with structured and text equality. | Confirmed in the signed-in CLI and wire trace. | Deferred. |
| Validation | Count `9` accepted. String `"9"` reached the server and returned `INVALID_INPUT`. | Valid input accepted. Wrong type, Boolean, extra field and range rejected at the server. | Valid input accepted. Client rejected wrong type, extra field and range before transmission. | Deferred. |
| Evidence paging | Both pages returned. The second call used the exact cursor from the first. | Both pages and expiry verified. | Both pages confirmed on build 0.1.1. | Deferred. |
| Server denial | `DENIED` and `protectedActions: 0` confirmed by client and server. | `DENIED` and zero protected actions. | `DENIED` and zero protected actions. | Deferred. |
| Actual response | Model response matched the tool results. Grok exposed JSON text. Separate structured content unverified. | Direct app-server results confirmed. Stage 0B included no model turn. | Confirmed model response. Separate structured content exposure unverified. | Deferred. |
| Shutdown | **Passed with the disposable supervisor.** All seven calls completed, the probe logged EOF and its launcher exited **0**. The independent native headless and ACP tests returned probe exit **1** without EOF. Native doctor logged EOF. | App-server exited **0** and probe PIDs were gone. Graceful EOF unverified on that route. | ACP exited **0** and probe logged EOF. | Fixture EOF confirmed in Stage 0B health checks. Model-route shutdown deferred. |

## Grok execution

The installed catalog confirmed an existing **grok.com** login. The successful command selected `grok-4.7` with low reasoning effort. Grok reported `grok-4.7-build` as the resolved model. The director approved trust for the disposable folder. Its project TOML registered the original launcher and disabled the unrelated plugin. The preflight showed one stdio MCP server, zero enabled plugins and zero hooks.

The command used `--no-auto-update`, `--permission-mode dontAsk` and five exact `MCPTool(wpai_probe__<operation>)` rules. Explicit denies covered shell, reading, editing, search and web access. The built-in list was restricted, and web search, memory and subagents were disabled. The ordinary Grok configuration hashes matched before and after the run. The evidence file has the exact argument vector, project configuration hash, client event IDs, result text and independent server events. [Grok headless scripting](https://docs.x.ai/build/cli/headless-scripting), [Grok permissions](https://docs.x.ai/build/features/permissions).

| Operation | Observed result |
|---|---|
| `probe_info` | Build `0.1.1`, contract `wpai.probe.v1` and negotiated `2025-11-25`. |
| `probe_echo` | `{"value":{"label":"WPAI","count":7,"enabled":true}}` |
| `probe_validation` | `{"valid":true,"count":9}` for `9`, and `{"code":"INVALID_INPUT","reason":"Expected an integer"}` for `"9"`. |
| `probe_evidence_page` | Page 1 returned `alder` and `birch`. The exact cursor yielded page 2 with `cedar` and `dogwood` and a null next cursor. |
| `probe_denied_operation` | `{"code":"DENIED","protectedActions":0}` |

Three distinct launch conditions were observed. The installed catalog lacked the documented `grok-build` alias and the first attempt stopped before MCP launch with `Invalid params: "unknown model id"`. The next attempt reached discovery using the installed default `grok-4.7`. Its Read deny blocked Grok’s generic `search_tool` and the subsequent unqualified `probe_info` call was cancelled by the headless dispatcher. A focused retry used full `wpai_probe__<operation>` catalog keys and inline inputs. It preserved all restrictions and reached the unchanged server. Client and server records account for seven calls. [Qualified Grok MCP names](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/07-mcp-servers.md).

Grok reported the exact managed-only policy value `off`. Stage 0B’s Boolean conversion of this field was unreliable because a nonempty enum string can evaluate as true. Folder trust was the observed Stage 0C launch prerequisite.

### Grok shutdown follow-up

The installed Grok ACP client advertised `sessionCapabilities.close`. A disposable session explicitly registered the same launcher and used existing cached OAuth. Its model test was withheld because the session reported no permission mode and `session/set_mode("dontAsk")` returned `-32602` with `unknown mode id: dontAsk`. No ACP model prompt was sent.

A separate control-plane test held a Windows handle to the live probe process. The unchanged probe negotiated `2025-11-25` and listed five tools. Grok acknowledged `session/close` with `x.ai/closeOutcome: closed`. Windows observed the probe exit with **code 1** before the ACP transport was closed. The probe recorded no EOF. The Grok ACP process itself later exited with **code 0**, with no probe process or listener remaining. This establishes non-graceful termination for the tested ACP control route. The original seven-call headless test’s probe exit code was not captured. A single-echo follow-up used the same subscribed headless route and held a Windows handle to the live probe before Grok exited. The probe returned the exact echo. Grok ended the turn and exited with **code 0**. Windows recorded the probe at **code 1** without EOF. No process or listener remained. The Grok doctor route was the only direct Grok launcher path tested here with verified EOF. [ACP session close](https://agentclientprotocol.com/protocol/v1/session-setup#close-session), [Grok ACP scripting](https://docs.x.ai/build/cli/headless-scripting).

### Grok supervised teardown

The two nonzero native exits are a process-lifecycle issue for this fixture. The disposable supervisor owns the original launcher outside Grok’s process tree. Grok launches a stdio relay. It carries bytes unchanged over a Windows named pipe configured for one instance, rejection of remote clients, and a one-time capability. A separate owner detects transport disconnect, closes the launcher’s stdin and waits for the original probe. No TCP listener, service, tunnel or MCP implementation was added. [Windows named pipe flags](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createnamedpipea).

A control test terminated its own relay after negotiating MCP. The probe logged EOF and the launcher exited 0. The live Grok test used the same auth route, exact five-tool allowlist and denial rules as the original qualification. It repeated all seven tool calls. The independent probe trace and Grok results agreed on the exact echo, valid input, invalid-input error, both pages and server denial with zero protected actions. After Grok disconnected, the supervisor closed stdin. The probe logged EOF, the unchanged launcher returned 0, and Grok exited 0. The check found no remaining owner, relay, launcher, probe process or recorded TCP listener. The disposable registration was restored, and normal configuration hashes matched. This verifies supervised shutdown. The two native failures remain recorded.

The replay driver remains in the existing disposable workspace at `work/stage-0b/stage_0c_stdio_owner.py`. Its SHA-256 is `729fe9c5f6b5cc38358e4ba6a5e0b15ce5c46a6a021b1ac13343198bd06430d3`. The evidence records the disconnect control, live results and an authorization control. A local client with an invalid per-run capability was rejected before the launcher or forwarding threads started. The one-shot pipe closed and could not be reopened. This check sent no model prompt. The one-time pipe capabilities are excluded.

## Subscription and token evidence

| Grok session | Input including cache | Cached input | Output | Reasoning | Reported model calls | CLI cost field |
|---|---:|---:|---:|---:|---:|---:|
| Cancelled dispatch attempt | 12,799 | 8,320 | 523 | 368 | 2 | $0.016256 |
| Successful qualified invocation | 20,338 | 8,832 | 863 | 209 | 3 | $0.032606 |
| Successful supervised invocation | 20,215 | 16,256 | 834 | 140 | 3 | $0.021050 |

The successful session reported **21,201 total tokens**. It took **14.403 seconds** from process start to exit. `grok usage <session_id>` confirmed the successful session totals. The stream separates uncached and cached input. Reasoning is a reported detail and is not added to the total again. The dollar amounts are CLI telemetry. An attributable subscription quota delta and invoice amount were unavailable. The run used the existing subscription authentication route and supplied no API key.

The separate shutdown echo took **5.449 seconds**. The CLI reported **12,963 total tokens** using `grok-4.7-build` and showed `0.012982` USD in its cost field. No attributable subscription quota delta was available. The supervised run took **15.269 seconds** and reported **21,049 total tokens** under the same model ID.

## Claude and Gemini disposition

Claude Code reported signed out. The director paused Claude because there was no eligible paid subscription. Its Stage 0B discovery and shutdown evidence remains intact. The installed client exposes `--mcp-config`, `--strict-mcp-config` and exact `mcp__<server>__<tool>` names for a future authorized model run. [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Claude Code headless execution](https://code.claude.com/docs/en/headless).

Antigravity remains the primary Google client. Legacy Gemini CLI **0.71.1** was supplemental in Stage 0B. Its `gemini mcp list` connected and pinged over `2025-11-25` after disposable folder trust. That subcommand supplied no catalog or invocation evidence. Gemini’s separate account and entitlement requirements still apply.

## Security and protocol decision

The probe rejected the deliberately denied operation before any protected action. The client allow rule permitted delivery of the synthetic request. The server remained the authorization boundary. After the tests, none of the recorded probe processes remained and their recorded PIDs owned no current TCP listener. No probe, production repository or normal agent configuration file was edited. Grok’s trust approval was scoped to the disposable fixture.

Retain **one local dual-era stdio artifact**. The Grok model run used legacy initialization. Antigravity used July 2026 discovery. Codex covered both. Keep JSON text alongside structured results because Grok’s verified endpoint exposed text. Put Grok’s qualified catalog names in its client profile and keep shared execution provider-neutral. The Python standard-library probe and the Stage 0B legacy SDK control support the spike. Choose a production SDK after it proves both dialects across the required client paths. [July 2026 stdio and backward compatibility](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio), [Python SDK protocol support](https://py.sdk.modelcontextprotocol.io/protocol-versions/).

## Stage 0C acceptance and next goal

**Passed:** Artifact integrity. Grok registration, discovery and seven actual calls. Exact echo, valid and invalid input, both evidence pages, server denial and zero protected actions. Client exit, child cleanup and verified normal Grok configuration hashes. Graceful probe shutdown passed through the disposable supervisor.

**Approved exception:** Claude Code actual model invocation, result reception, server denial and model-route shutdown remain unverified. The four-client technical result still depends on a future Claude run. The director confirmed “Claude is defferd. Continue past it. Gap noted an approved.” on November 26, 2026. This closes the current handoff with the documented exception and moves the full unchanged-fixture Claude test to far-future work. Grok’s verified supervised route closes the fixture cleanly. Its native direct launch still lacks graceful shutdown evidence.

**Stage 1 gate accepted on November 26, 2026:** The director said “Note the gap for far future work and continue.” This accepts the remaining Claude limitation for proceeding to Stage 1. The first Stage 1 operation is read-only `repo_health_v1` against one allowlisted checkout. Acceptance requires all twelve W1 field dispositions, agreement with an independent Git/GitHub comparison, bounded output and runtime, denial before subprocess launch, and one shared stdio adapter.

### Evidence check and deferred Claude acceptance

The offline handoff check rehashed all 18 Stage 0B manifest entries, compared the resident probe and launcher byte for byte, matched seven Grok client results to corresponding server events, and checked denial, EOF, cleanup and token totals. The same check verified that Claude’s two retained Stage 0B records contain discovery and EOF without any tool-call event. The original Stage 0C run record captures the earlier pre-approval state. The director’s later decision above governs this handoff.

Resume the Claude test when the director authorizes an eligible existing subscription. Use the unchanged Stage 0B archive and launcher, a disposable working directory, strict MCP configuration and permissions scoped to the five probe tools. Record the installed CLI and model versions, permission decisions and negotiated protocol from the actual run.

Close the acceptance item when the client and independent server evidence jointly establish the exact echo, valid count `9`, the invalid string count disposition, both cursor-linked pages and denial with `protectedActions: 0`. If the client rejects the invalid input before transport, record that as client-side validation. Capture which result representations the client exposes, the model’s final response, actual process exits, probe EOF and child cleanup, plus any usage the CLI exposes. Ordinary client configuration must remain intact.

The Stage 0C audit used WPAI Constitution **v6.24.0** at accepted SHA `0adf5ecee5f7f96ce3749944dc097a003731a6e9`, with 23 binding files verified. Constitutional evolution was outside the Stage 0C write scope. The separate Stage 1 handoff records implementation and verification of W1.

# Stage 1.3 offline measurement handoff

Stage 1.3 implemented a Windows stdio supervisor for the synthetic fixture, an independent comparator, and a deterministic plan for a paired study. It used zero live model sessions. The native teardown and future inference gates remain open.

The starting repository `main` was `c8c9900e95007960e84a2fb364a8ca8551531d82`. The live default branch and the local and remote branch inventories agreed. The accepted WPAI Constitution was v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9`. The frozen loader verified all 23 binding files. Stage 1.3 explicitly excluded Constitution amendments. [Accepted Constitution revision](https://github.com/MrWizard94-Compile/Agents-Constitution/tree/0adf5ecee5f7f96ce3749944dc097a003731a6e9)

## Stage 1.2 reconciliation

All six selected runs returned twelve exact facts. The expected client starts, completion statuses, server requests and oracle reply digests independently support twelve control operations and one treatment operation for each route. Aggregate and per-field replies both match the synthetic oracle. [Reconciliation and original run-byte digests](reconciliation.json) · [Original Stage 1.2 records](../stage-1.2/)

| Route | Stage 1.2 pair | Result and shutdown evidence |
|---|---|---|
| Codex | Matched and accurate | Client result events and exact server digests. Fixture roots seen gone. The records have no server stop event, EOF observation or server exit code. |
| Antigravity | Matched and accurate | Client completion statuses, exact server digests and exact final answers. Separate client result bytes were unavailable. Stage 1.2 reported clean EOF and exit 0. Both raw server traces show application return code 0 and a stopped worker. The stop event lacks a termination reason, an independent OS exit code, and tree ownership evidence. |
| Grok | Ineligible | Both answers and expected benchmark calls were correct. The control additionally emitted `unqualified_or_unapproved_search_tool`. The fixture roots were seen gone with no server stop event, EOF observation or server exit code. |

The comparator preserves the six discarded attempts and their original hashes. Three Antigravity permission attempts reached discovery and then recorded a cancelled permission decision, including the failed treatment. Two other Antigravity attempts ended before the model started. The earlier Grok control was cancelled after out-of-scope activity. [Discarded attempts](../stage-1.2/attempts/)

The new report independently recomputes every archived reduction from raw records. The archived reduction block describes the pilot under its original evidence threshold. The Stage 1.3 resource gate requires clean lifecycle proof and comparable telemetry in both arms. No archived pair clears that gate. Codex and Grok expose client events with result presence. Their normalized records omit a numeric client-side byte count. Server JSON and wire bytes have separate fields. [Recomputed comparison](reconciliation.json)

## Native teardown and offline evidence

**Codex.** The exact CLI release used in the pilot, 0.166.0, has a Windows MCP launcher that owns a Job Object or a process handle. Its local standard transport closes by terminating the owned process before closing the transport. The process handle also invokes Windows termination on drop. This is a source-backed explanation for how the process can disappear before the fixture records EOF. The actual Stage 1.2 shutdown path remains unobserved. [Codex release source](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/rmcp-client/src/stdio_server_launcher.rs#L219-L242) · [Windows termination implementation](https://github.com/openai/codex/blob/6ff1e1ca3b30fc8b914720681fcf5fe62e95f856/codex-rs/rmcp-client/src/stdio_server_launcher.rs#L715-L739)

**Grok.** Earlier Windows Stage 0C evidence independently observed exit code 1 and no EOF on the native ACP session-close and headless routes. A separate owner placed outside Grok's client tree observed EOF and exit 0 using the same probe through a relay. That experiment establishes what happened to the Stage 0C probe. The Stage 1.2 native server still has no observed OS exit code or EOF. [Stage 0C compatibility evidence](../wpai-stage-0b-0c-compatibility.md#grok-shutdown-follow-up) · [Supervised Stage 0C proof](../stage-0c-grok-supervised-evidence.json)

**Synthetic supervisor.** The tests cover regular client EOF, server-initiated exit with an open client pipe, early stdin close, a client process exiting before reply, server crash, broken output pipe, partial reads and writes, malformed JSON-RPC on the pinned fixture, a worker failure on that fixture, timeout, cancellation, and forced cleanup with a live descendant. Additional cases cover an abandoned descendant, unread output, and a synthetic outer job killing both the in-band wrapper and its fixture. The outer job verified zero remaining processes and the wrapper produced no lifecycle receipt. This demonstrates the evidence gap when a provider owns and terminates the entire in-band process tree. Future qualification can use an independent owner where needed. [Supervisor tests](../../work/benchmarks/stage-1.3/tests/test_supervisor.py)

## Usage and future authorization

The usage reference contains raw input, cache reads and writes, output, reasoning, total tokens, model calls, agent turns, elapsed times, operations and cost telemetry where observed for each selected arm. Codex's total is derived from recorded input plus output. Antigravity's provider-specific input partition remains unresolved. Grok's USD field is client-reported telemetry. Attributable subscription quota, billed charges and pure model latency are unavailable across all three routes. [Historical usage by route and arm](usage-reference.json)

**Authorization gate.** Future live inference requires explicit authorization naming the routes and the session budget. First qualify lifecycle capture on each route. Grok also requires a clean control with no extra tool activity before entering resource comparison. Qualification runs require separate authorization and fall outside the schedule. Each route has five pairs and ten sessions. After lifecycle qualification, Codex and Antigravity would require twenty sessions together. A requalified Grok route would bring the total to thirty. Stage 1.3 authorized zero of these sessions.

The schedule records the seed, a two/three order split per route, independent context IDs and stable per-arm fingerprints for the model, available settings, client version, protocol, prompt, dataset, response schema and package. Keep metrics and descriptive statistics provider-specific. Five pairs support descriptive medians and ranges. They do not establish statistical significance, universal performance or generalizable savings. [Plan and authorization conditions](repeatability-plan.json) · [Reproduction and analysis](../../work/benchmarks/stage-1.3/README.md)

## Acceptance matrix

PASS identifies an observed Stage 1.3 result. FAIL identifies a criterion contradicted by evidence. OPEN identifies a qualification or dependency awaiting evidence or authorization.

| Criterion | State | Evidence |
|---|---|---|
| A01 Repository and Constitution baseline | PASS | Live target, single branch inventory, clean start and frozen accepted source verified. |
| A02 Preserve Stage 1.2 byte-for-byte | PASS | Original Git blobs retained and all twelve raw records independently hashed. |
| A03 Reconcile route dispositions | PASS | Six selected runs and six discarded attempts reconciled. |
| A04 Separate outcomes | PASS | Answer, tool execution, lifecycle, pair and resource gates are independent. |
| A05 Investigate native Codex and Grok | PASS | Exact Codex release source, Stage 0C evidence and offline teardown experiments explain the gaps. Native qualification remains open. |
| A06 Preserve protocol bytes | PASS | Byte-for-byte relay with real pipes and injected partial I/O. |
| A07 Bounded failure handling | PASS | EOF, disconnect, cancellation, crashes, broken pipes, blocked output and timeout tested. |
| A08 Distinguish natural and forced | PASS | Natural exit 0, exit 7, graceful cancellation and job termination observed separately. |
| A09 Verify tree cleanup | PASS | Windows Job Object confirmed zero active members, including tests with descendants. |
| A10 Offline lifecycle matrix | PASS | Fifteen supervisor tests on both supported Python versions. |
| A11 Fail closed | PASS | Regressions cover failed or unfinished operations, unexpected tools, invalid digests, inconsistent settings and forged-looking flag combinations. |
| A12 Missing telemetry | PASS | Missing, nonfinite and boolean counters handled without implied zeros. |
| A13 Grok exclusion | PASS | Additional control search retained. Both reduction blocks are empty. |
| A14 Antigravity result bytes | PASS | Client result bytes unavailable alongside independently valid server replies. |
| A15 Recalculate archived comparison | PASS | All original reduction fractions match the independent raw-record calculation. |
| A16 Deterministic schedule | PASS | Fixed-seed generation is reproducible. |
| A17 Randomized balanced order | PASS | Each route has two or three control-first pairs across tested seeds. |
| A18 Plan-only isolation | PASS | Both entry modes ran with process and socket entry points blocked. |
| A19 Future session accounting | PASS | Ten sessions per route and separate authorization for qualification. |
| A20 Python 3.10 and 3.14 | PASS | On each version, 21 Stage 1.1 tests, the Stage 1.2 verifier and 26 Stage 1.3 tests passed with warnings as errors. |
| A21 Offline CI security | PASS | Windows matrix retains existing action pins, read-only permissions and disabled credential persistence. |
| A22 Dependencies | PASS | Python standard library only. |
| A23 Scope and usage | PASS | Zero live invocations. Synthetic inputs only. Existing authentication and provider settings untouched. |
| A24 Publication review | PASS | Candidate changes and generated evidence reviewed. Historical files and archives preserved. |
| A25 Explicit handoff state | PASS | Accepted checks and open qualifications are listed here. |
| Native MCP lifecycle qualification | OPEN | The offline supervisor is verified. Future authorization and route-specific capture are required. |
| Grok clean control for resource comparison | OPEN | Stage 1.2's extra search remains disqualifying. |
| Repeatability study and full upstream schema validation | OPEN | The study is plan-only. The full upstream validator remains deferred. |

## Stage 1.3.1 correction

The [Stage 1.3.1 handoff](../stage-1.3.1/handoff.md) records the Windows cancellation and comparator fixes. The historical observations and acceptance findings above describe Stage 1.3. New lifecycle claims require a v2 receipt and verified termination of all three pumps.

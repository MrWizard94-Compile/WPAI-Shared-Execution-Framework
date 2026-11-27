# Stage 1.2 synthetic agent benchmark

## Scope and reproducibility

The clean local and remote starting point was `d3b513aa1bff5ef44879950393b5f3d3946b2c95` on the existing `main`. The frozen WPAI Constitution was v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9`. The loader and 23 verified files matched that revision. Constitution amendments were excluded by the director. All project changes are test infrastructure or benchmark evidence. The production framework and historical evidence remain byte-identical.

The fixture verified the accepted Stage 1.1 ZIP SHA-256 `9063cd629145fee025a6330dd969a6bb608bc2571cca72dde5860947652a3686` and all six listed members before using its original `Stdio` and result handling. The server injects a fixed synthetic acquisition function and fictional tool catalog metadata before starting the original adapter. The test treatment preserves the production `repo_health_v1` contract and names a fictional selector. The test control needs twelve individual `fixture_read_field_v1` calls. Both return the exact same twelve fact objects. [Reproduction](../../work/benchmarks/stage-1.2/README.md).

The independent fictional ground truth has SHA-256 `1eb47cd4ebc554a490b3cc439440f927fced1cc052aa3d634cdd2e97941092f8`. The model receives only the benchmark task and the synthetic tool response data from a disposable workspace. It has no live project acquisition route. The validator rejects invalid JSON, duplicate members, unsupported fields, changed numeric types, mismatched SHAs and changes to empty or unavailable facts. [Dataset](../../work/benchmarks/stage-1.2/ground_truth.json) · [Response schema](../../work/benchmarks/stage-1.2/response_schema.json) · [Artifact and prompt SHA-256 values](identities.json) · [Control prompt](control-prompt.txt) · [Treatment prompt](treatment-prompt.txt).

The Python 3.10 and 3.14 offline verifier passed both arms on all three MCP revisions with warnings as errors. The six direct combinations checked authorization, exact fact equality, result parity and clean EOF. The existing Python 3.14 Stage 1.1 suite passed all 21 tests. Offline RPC helps verify fixture behavior. The native client evidence below comes from actual subscribed model turns.

## Client dispositions

| Client | Installed version | Model | MCP version | Disposition |
|---|---|---|---|---|
| Codex CLI | 0.166.0 | `gpt-6.1-sol`, explicit CLI model selection, low | `2025-06-18` | Actual model-issued invocations and a valid matched pair. Treatment ran first. |
| Grok Build | 1.0.92 | `grok-4.7-build`, reported by the client, low | `2025-11-25` | Actual calls and exact answers in both arms. Control ran first. The routed control included one additional built-in lookup start. |
| Antigravity CLI | 1.5.18 | `gemini-4-neon-high`, current ACP session model, separate reasoning setting unavailable | `2026-07-28` | Actual calls and exact answers in both qualified arms. The first control attempts exposed tool-name permission matching failures. The director authorized one additional control-only run after the treatment proved the corrected matcher. The selected treatment therefore ran first. |
| Gemini CLI | 0.71.1 | Unavailable | Unavailable | DEFERRED — Gemini CLI model invocation requires separately authorized authentication. Its supported OAuth configuration and credential file were absent. |
| Claude Code | 2.1.243 | Unavailable | Unavailable | DEFERRED — Claude Code model-level invocation remains an approved open item. |

## Measurement and provenance

The runner records each client process, its selected model and exposed settings, installed version, and invocation events separately from the fixture’s own acquisition events and exact reply digests. For an accepted run, those digests match an independent reproduction of the expected reply objects. Codex and Grok emitted client tool-result events. Antigravity exposed completion status and the exact model answer. Its separate tool-result bytes were unavailable to the ACP observer. Raw transcripts, account state, process identifiers and credential values are excluded from the public records. [Run records](runs/) · [Preserved earlier attempts](attempts/) · [Machine-readable comparison](comparison.json).

Whole-run time is the monotonic interval from client preflight through exit. Provider-phase time is recorded separately where the driver captured it. Fixture round trip covers receipt of a complete request line through STDOUT delivery, summed over the tool replies. Acquisition and JSON serialization are separate monotonic measurements. The payload bytes count JSON result text once, while wire bytes include the outer envelope and both projections. All fixture acquisitions attempted zero underlying Git or GitHub operations. No reliable maximum memory sample or separate tool-round boundary was available. Provider model-call counts and agent turns remain distinct.

Codex input includes cached input. Its combined total is derived by adding output to input. Grok reports uncached input separately. The consolidated input shown sums uncached input, cache reads and cache creation. Antigravity usage is retained in its original ACP counters because its input partition is provider-specific. Reasoning counters are preserved without adding them twice to reported totals. Grok’s USD values are CLI telemetry. Billing and attributable subscription quota deltas were unavailable. All model trials used the existing subscription routes.

### Observed paired results

Cells show control → treatment. Every selected arm completed with client exit 0 and matched all twelve fields. Each selected control returned the twelve ordered field digests and each treatment returned the single complete digest. The Grok control also started one built-in lookup. Its outcome was unobservable, so Grok resource deltas are descriptive and excluded from the reduction calculation.

| Measure | Codex CLI | Grok Build | Antigravity CLI |
|---|---:|---:|---:|
| Exact W1 fields | 12/12 → 12/12 | 12/12 → 12/12 | 12/12 → 12/12 |
| Confirmed benchmark MCP calls | 12 → 1 | 12 → 1 | 12 → 1 |
| Successful fixture calls | 12 → 1 | 12 → 1 | 12 → 1 |
| Failed fixture calls | 0 → 0 | 0 → 0 | 0 → 0 |
| Client result-bearing tool events | 12 → 1 | 12 → 1 | Unavailable → unavailable |
| Client completed tool events | 12 → 1 | 12 → 1 | 12 → 1 |
| Agent turns | 1 → 1 | 14 → 2 | 1 → 1 |
| Provider model calls | Unavailable | 14 → 2 | Unavailable |
| Tool-call rounds | Unavailable | Unavailable | Unavailable |
| JSON result bytes | 3,679 → 3,170 | 3,679 → 3,170 | 3,679 → 3,170 |
| Tool reply wire bytes | 9,196 → 6,843 | 9,196 → 6,843 | 10,517 → 6,953 |
| Whole run with preflight, seconds | 54.274 → 32.833 | 36.084 → 21.436 | 85.131 → 28.008 |
| Provider phase, seconds | Unavailable | 33.371 → 18.744 | 83.219 → 26.279 |
| Fixture tool round trip, summed ms | 6.6567 → 0.6800 | 8.1561 → 0.7941 | 6.3298 → 0.7285 |
| Fixture acquisition, summed ms | 0.0827 → 0.0109 | 0.1426 → 0.0123 | 0.0863 → 0.0085 |
| JSON serialization, summed ms | 0.4598 → 0.1318 | 0.7832 → 0.1709 | 0.4569 → 0.1537 |
| Acquisition process attempts | 0 → 0 | 0 → 0 | 0 → 0 |
| Input tokens, raw provider counter | 165,509 → 34,302 | 14,261 → 6,478 | 40,703 → 13,614 |
| Input including known cache | 165,509 → 34,302 | 112,821 → 15,054 | Unavailable |
| Cache-read input tokens | 144,256 → 30,720 | 98,560 → 8,576 | 141,459 → 11,019 |
| Cache creation or write tokens | 0 → 0 | 0 → 0 | 0 → 0 |
| Output tokens | 1,622 → 1,203 | 2,184 → 1,695 | 4,316 → 3,229 |
| Reasoning or thought subcounter | 0 → 0 | 442 → 423 | 2,526 → 1,945 |
| Total tokens | 167,131 → 35,505 derived | 115,005 → 16,749 reported | 186,478 → 27,862 reported |
| Provider cost field, USD | Unavailable | 0.090906 → 0.027414 | Unavailable |

For the comparable Codex pair, the observed reductions were 91.7% in MCP calls, 78.8% in total tokens and 39.5% in whole-run time. For the comparable Antigravity pair, they were 91.7%, 85.1% and 67.1%, respectively. These percentages describe these individual trials. They leave caching, setup, model and order variation unresolved. Both clean pairs happened to run treatment first after the approved Antigravity correction. Neither comparable pair exposed a cost field. The earlier denied attempts and the Grok routing correction are retained separately from the selected measurements.

## Security and open technical limits

The exact nested Stage 0B member has seven local path-account matches. Its published counterpart has seven approved placeholder substitutions and no unredacted matches. Historical archive and source bytes are preserved. The upstream MCP JSON Schema revision and hashes are recorded, alongside the rationale for deferring an offline full-schema dependency. [Audit follow-up](audit-followup.md).

The process checks verified that recorded fixture processes were gone and disposable configurations were removed. The Codex and Grok live routes ended without an observed fixture stop event. Their fixture exit codes are unavailable. The Antigravity route recorded EOF and fixture exit code 0. Direct offline fixture tests recorded EOF across all three revisions. Native termination behavior remains an integration variable.

This is a single-pair pilot. A later study should start with five randomized, matched pairs per eligible route and consider ten when variation and quota permit. Runs should keep model, effort, fingerprints and observed permission behavior fixed. Recommended Stage 1.3 scope is to validate clean native teardown, validate the repeatability of the supported agent routes, and evaluate variance on the same synthetic task. Keep measured tool-call savings separate from model cost and speed claims.

## Acceptance

| ID | Status | Evidence |
|---|---|---|
| A01 | PASS | Frozen accepted Constitution and current framework governance verified. |
| A02 | PASS | Exact Stage 1.1 ZIP and all six manifest entries verified. |
| A03 | PASS | Fixed fictional twelve-field dataset. Six offline arm/revision checks returned it deterministically. |
| A04 | PASS | Ground-truth SHA-256 and byte identity independently verified. |
| A05 | PASS | Both arms returned identical facts and provenance. Selected server reply digests independently matched. |
| A06 | PASS | Control catalog exposes one field per call and all three selected controls retrieved twelve fields in order. |
| A07 | PASS | Treatment launches original packaged Stage 1.1 `Stdio` and aggregate result handling around a synthetic acquisition function. |
| A08 | PASS | Synthetic-only prompts and result evidence, isolated empty workspaces, bounded catalog and external-acquisition guard. |
| A09 | PASS | Grok issued twelve and one benchmark calls. The extra control lookup limits resource comparisons. |
| A10 | PASS | Codex CLI issued twelve and one benchmark calls through actual model turns. |
| A11 | PASS | Antigravity ACP issued twelve and one benchmark calls through actual model turns. |
| A12 | PASS | Separate Gemini CLI version checked. Model invocation is deferred under the required authentication rule. |
| A13 | PASS | Claude model invocation retains its approved deferral. |
| A14 | PASS | Six selected measurements have client start/completion evidence and matching independent server events. Earlier failures are retained as attempts. |
| A15 | PASS | Disposable configurations exported one exact scoped MCP operation per arm. Grok reported one unmatched built-in lookup start. |
| A16 | PASS | All six measurements identify the model selection or report source, protocol and reasoning availability. |
| A17 | PASS | Independent strict validator checked all twelve fields, missing/extra keys, exact SHAs, number types and unavailable status. |
| A18 | PASS | Tool events, model calls, turns, elapsed time, fixture work and payload sizes have separate counters. |
| A19 | PASS | Provider usage fields and Grok cost telemetry preserved with their accounting boundaries. |
| A20 | PASS | Unavailable counters and separate Antigravity result bytes are explicitly labeled. |
| A21 | PASS | Existing subscription routes, no paid API requests, no manual authentication changes and unchanged observed settings or credential files. |
| A22 | PASS | Single-pair differences labeled observational. Confounded Grok resource reductions withheld. |
| A23 | PASS | Seven exact local archive path matches reconciled to the approved published placeholders. |
| A24 | PASS | Pinned upstream schema hashes recorded and full offline-schema CI gate separately deferred with rationale. |
| A25 | PASS | Fixture process identifiers verified gone, clients exited, and disposable directories removed. Native EOF visibility is tracked separately. |
| A26 | PASS | Reviewed normalized records exclude auth values, raw transcripts, personal paths and unauthorized project values. |
| A27 | PASS | Reproduction steps, actual observations, limitations and later study plan committed. |
| A28 | PASS | Main-only project diff consists of benchmark infrastructure, evidence and the project index. |

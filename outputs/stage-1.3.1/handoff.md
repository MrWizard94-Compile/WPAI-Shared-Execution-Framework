# Stage 1.3.1 supervisor and evidence handoff

Stage 1.3.1 corrects the Windows stdio supervisor and the evidence parser. It adds the v2 lifecycle receipt and a validated offline merge. The accepted starting `main` was `ec7ea9d5c88a6d8adee65fd2fd5518947f39a687`. The canonical Constitution was verified at `0adf5ecee5f7f96ce3749944dc097a003731a6e9` with all 23 frozen bindings. The stage excluded amendments and used zero live model sessions. [Frozen Constitution](https://github.com/MrWizard94-Compile/Agents-Constitution/tree/0adf5ecee5f7f96ce3749944dc097a003731a6e9)

The Stage 1.3.1 supervisor resolves the Win32 no-pending-I/O race while retaining other cancellation and pipe errors. It tracks three threads separately from the owned Windows process tree. It gives every outstanding pump a bounded chance to finish or cancel, then records any thread still alive. Tests include an actual pending Windows output write at peer disconnect, a full unread stdout pipe, a blocked write to the child, and a deliberately unresponsive output pump. The unresponsive pump case verified that the tree can be gone while lifecycle still fails. The in-band wrapper can still be killed by an outer owner before writing a receipt. [Corrected tools and receipt contract](../../work/benchmarks/stage-1.3.1/README.md) · [Microsoft cancellation contract](https://learn.microsoft.com/en-us/windows/win32/fileio/cancelsynchronousio-func)

The v2 comparator reports unavailable, invalid and observed telemetry independently. It requires clean, associated v2 lifecycle proof before admitting a future pair. The original Stage 1.2 reductions, Grok exclusion, Antigravity result-byte limitation, and historical lifecycle-open findings were regenerated and checked against the archives. The five-pair schedule and authorized session count of zero were verified by hash. Forty-five files under the Stage 1.2 and 1.3 directories matched their accepted bytes in full. The Stage 1.3 README and handoff retain all original bytes and add a pointer to this correction. The manifest records both the full-file hashes and the original documentation byte ranges. [Historical SHA-256 inventory](historical-sha256.json) · [Reproducible outcome and source hashes](verification.json)

## Acceptance matrix

PASS means the scoped check was verified. FAIL means evidence contradicted the criterion. OPEN marks a qualification or observation that is still outstanding.

| Criterion | State | Evidence |
|---|---|---|
| A01 Repository and Constitution baselines | PASS | Verified the live branch, exact starting commit, clean tree and frozen accepted Constitution. |
| A02 Preserve Stage 1.2 and 1.3 evidence | PASS | All historical source and measurement artifacts hash-match. The two documentation additions preserve the original bytes as prefixes. |
| A03 Benign `ERROR_NOT_FOUND` | PASS | A controlled Win32 response leaves the stop signal set and adds zero transport faults. |
| A04 Other cancellation errors | PASS | Injected access denial is recorded once per pump and prevents clean transport. |
| A05 Idempotent cleanup | PASS | Repeated stop calls, an exit during cancellation and normal completion after a cancellation request are covered. |
| A06 Explicit thread accounting | PASS | Receipts report started, stopped, verified stopped and outstanding pump names. |
| A07 Live pump prevents success | PASS | Deliberately unresponsive stdout leaves lifecycle false despite an empty Job Object. |
| A08 Bounded cleanup | PASS | Real blocked input and output, broken pipe, pending-write disconnect, timeout and cancellation cases quiesce or report the outstanding pump. |
| A09 Deterministic cancellation tests | PASS | Win32 outcomes are injected under explicit synchronization. |
| A10 Distinct collection states | PASS | Omitted, null, invalid, empty and nonmatching events were exercised independently. |
| A11 Missing telemetry stays unavailable | PASS | Invalid or missing counts are null. Observed empty collections count as zero. |
| A12 Incomplete run gates | PASS | Missing starts, completions, scope and server trace invalidate execution and pairing. |
| A13 Explicit receipt handoff | PASS | A real synthetic wrapper receipt merged through the CLI into a separate file and passed lifecycle validation. |
| A14 Run ID, arm and fixture identity checks | PASS | Comparator and merge reject mismatches. The helper also rejects a preexisting lifecycle member. |
| A15 Original comparison results | PASS | Corrected v2 replay matches all historical reduction fractions. |
| A16 Grok exclusion | PASS | Out-of-scope control search remains independently disqualifying. |
| A17 Antigravity byte availability | PASS | Client result bytes remain unavailable. |
| A18 Schedule and authorization | PASS | Original schedule bytes, five pairs per route and zero authorized sessions verified. |
| A19 Warnings-as-errors verification | PASS | Both pinned Python versions passed 21 Stage 1.1 tests, the Stage 1.2 verifier, 26 Stage 1.3 tests and 50 Stage 1.3.1 tests. |
| A20 Windows CI security | PASS | Both pins, read-only contents access, disabled persistence and offline checks are retained. |
| A21 Evidence reproducibility | PASS | Both Python versions regenerated identical Stage 1.3 and Stage 1.3.1 evidence. |
| A22 Scope and inference | PASS | Local synthetic fixtures only. Zero provider sessions and no unauthorized private data. |
| A23 Final acceptance accounting | PASS | Scoped checks and qualification boundaries recorded here. |
| Hosted check for the final commit | PASS | [Windows tests run `45989981185`](https://github.com/MrWizard94-Compile/WPAI-Shared-Execution-Framework/actions/runs/45989981185) was triggered by a push to `main` at head SHA `eac62f37116383cbb65b50415b7056b44340613c` and concluded `success`. The Python 3.10.11 and Python 3.14.3 jobs both concluded `success`. The `Verify Stage 1.3.1 offline corrective tests and evidence` step concluded `success` in both jobs. |
| Native lifecycle and paired study | OPEN | Existing provider qualifications remain separate from offline synthetic validation. |

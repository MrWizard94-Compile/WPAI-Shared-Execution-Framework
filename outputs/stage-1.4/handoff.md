# Stage 1.4 offline lifecycle witness handoff

The independent Windows observer retained trustworthy exit and process-tree evidence after an external owner killed the unchanged Stage 1.3.1 wrapper and its pinned synthetic MCP server. The same event remained a lifecycle failure. The wrapper and server handles signaled, both exit codes were `124`, and the target Job Object reported zero active members. The observer remained outside that job and finalized its ledger after the termination owner also exited. The in-band wrapper produced no v2 receipt. [Normalized evidence](evidence.json) · [Architecture and observation sources](architecture.md)

The wrapper's external stdout returned Windows error `109` when the observer read after the force request. The observer recorded that pipe closure and left graceful EOF unverified. Its handle to the inner server supports the exit observation. The inner server's private stdin and stdout were not visible to this observer. Separate trusted synthetic actors verified normal stdin and stdout EOF with dedicated control pipes and actual terminal reads. [Versioned record and reproduction](../../work/benchmarks/stage-1.4/README.md)

## Baseline and verification

The live project baseline was `a4dbdb46ddcac40ee701773e328b725cb0eba954` on the sole branch, `main`. The accepted Constitution was v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9`, with all 23 frozen binding hashes verified. Previous Stage 1.2, 1.3 and 1.3.1 artifacts and source are covered by the original-byte inventory. The unchanged repeatability schedule retains `authorized_now: 0` and requires separate future approvals. [Historical SHA-256 inventory](historical.sha256) · [Stage 1.4 SHA-256 manifest](manifest.sha256)

On Windows with Python 3.10.11 and 3.14.3, local warnings-as-errors verification passed 21 Stage 1.1 tests, the Stage 1.2 fixture verifier, 26 Stage 1.3 tests, 50 Stage 1.3.1 tests, and 22 Stage 1.4 tests. Both runtimes verified the Stage 1.3 and Stage 1.3.1 evidence and reproduced Stage 1.4 normalized evidence. The Windows workflow retains its pinned actions, read-only contents access and disabled credential persistence.

## Synthetic scenarios

PASS means the test observed the expected result. Negative cases such as witnessed lifecycle failure, missing evidence, invalid identity and incomplete observation are successful tests of the witness.

| # | State | Verified result |
|---|---|---|
| 1 | PASS | Both synthetic actors reported an empty stdin read and the observer confirmed terminal stdout reads with clean exits. |
| 2 | PASS | Natural server exit returned code `0` from its signaled handle. |
| 3 | PASS | Natural server exit returned code `7`, with graceful synthetic EOF independently observed. |
| 4 | PASS | The server's retained handle was unsignaled after wrapper death. The target job still had one active member. |
| 5 | PASS | Separate owner killed the unchanged wrapper and its pinned synthetic server before in-band receipt creation. |
| 6 | PASS | Observer finalized after independent wrapper, server and owner exit observations. |
| 7 | PASS | A real descendant remained active after wrapper exit `0`, then its retained handle reported forced exit. |
| 8 | PASS | Closing the live server's observer-side stdout reader gave an explicit local-close observation with no terminal read. |
| 9 | PASS | The control pipe closed without an EOF attestation. The run stayed `unavailable` despite zero process exits. |
| 10 | PASS | Actual observer process exited `91`. The persisted prefix stayed `incomplete` and the parent guard reached zero active members. |
| 11 | PASS | Missing registration and signaled-without-exit-code scenarios separately stayed `unavailable`. |
| 12 | PASS | Reopening the real synthetic PID with a mismatched creation identity was rejected. |
| 13 | PASS | The bounded wait expired on a blocked worker and recorded timeout before forced cleanup. |
| 14 | PASS | Job accounting reported zero active members while the independent observer could still write and finalize. |

## Acceptance

| Criteria | State | Evidence |
|---|---|---|
| A01–A02 | PASS | Stage and governance baselines verified, and prior evidence checked byte-for-byte. |
| A03–A04 | PASS | The observer's checked ownership boundary survived wrapper and owner termination. |
| A05–A08 | PASS | Retained identities and handles, actual exit codes, raw pipe outcomes and job counts were verified independently. |
| A09–A11 | PASS | Append-only witness ledger survives the target. Invalid, absent, and incomplete evidence cannot yield clean lifecycle. |
| A12 | PASS | All fourteen synthetic requirements are covered by the scenario tests. |
| A13–A15 | PASS | Local pinned runtimes, prior suites, normalized evidence and the exact manifest verified. |
| A16–A18 | PASS | Zero live model sessions. Frozen plan, session budgets and separate route gates retained. |
| Native provider lifecycle qualification | OPEN | Unstarted and unauthorized. Each native route needs separate authorization and observation. |
| Paired study | OPEN | Unstarted and unauthorized. The next human decision is whether to authorize specific routes and a separate qualification budget. |

## Hosted verification

The hosted Windows workflow result is recorded against the implementation commit after publication.

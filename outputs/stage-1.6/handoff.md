# Stage 1.6 synthetic split-route lifecycle preflight

Windows processes exchanged the exact frozen synthetic response through the split relay. The observer measured each owned job, retained the process handles, classified each terminal pipe read, and validated its ledger after controlled cleanup. **Codex CLI, Antigravity CLI and Grok Build remain NO-GO for native qualification.** Zero provider sessions ran and `authorized_now` remains `0`. [Architecture and witness contract](architecture.md) · [Normalized evidence](evidence.json).

| Scenario | Lifecycle | Qualification evidence |
|---|---|---|
| Normal completion | `observed_success` | All six terminal pipe reads, genuine fixture-side EOF, four exits at 0, both jobs empty, witness finalized. |
| External termination | `observed_failure` | Root and relay exited 124. The owner and server remained alive and outside the subject job. The owner then closed the fixture writer and the server reached EOF and exited 0. Three subject-side reader outcomes remain unavailable. |
| Duplicate writer | `observed_success` | The server remained active with no terminal report while its duplicate writer stayed open. The final close permitted the actual empty read. Both jobs emptied normally. |
| Fixture-owner loss | `incomplete` | Owner exited 125 and its control reader returned terminal status 109. The observer forced owned cleanup, verified both jobs were empty, and finalized without claiming fixture EOF. |

## Acceptance

| ID | State | Evidence |
|---|---|---|
| A01 | PASS | Project baseline `b6366372f3a6e877db48616c115d24c6cd05558c` and accepted Constitution v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9` verified. |
| A02 | PASS | Zero provider sessions, no provider credentials or configuration used, and zero change in authorization. |
| A03 | PASS | Distinct observer, synthetic root, relay, fixture owner/server and external force controller ran as applicable. |
| A04 | PASS | Subject and fixture have distinct bounded jobs and verified membership and final accounting. |
| A05 | PASS | One-use anonymous local pipe pairs with explicit inheritance allowlists. |
| A06 | PASS | Fixed request and response matched byte counts and SHA-256 at all twelve boundaries. |
| A07 | PASS | Normal fixture EOF attested at its actual reader; output terminal read and actual exits separately observed. |
| A08 | PASS | Forced subject exits observed independently of live owner, server and observer. |
| A09 | PASS | Fixture writer closed by owner after subject termination, before genuine fixture EOF. |
| A10 | PASS | Bounded duplicate-writer negative control delayed EOF until final close. |
| A11 | PASS | Owner loss and independent fixture job recovery left both jobs empty and the case incomplete. |
| A12 | PASS | Versioned, bounded and durable witness with separate semantic validation. |
| A13 | PASS | Rechained mutated records and malformed integrity inputs rejected. |
| A14 | PASS | 97 earlier-stage source and evidence files verified against baseline bytes. [Historical hashes](historical.sha256) |
| A15 | PASS | Deterministic evidence and complete SHA-256 inventory verified. [Stage manifest](manifest.sha256) |
| A16 | PASS | All existing and Stage 1.6 checks passed locally on Windows with Python 3.10.11 and 3.14.3. |
| A17 | PENDING | Exact hosted Windows implementation result will be recorded here after success. |
| A18 | PENDING | Exact hosted closeout result is verified independently after publication. |
| A19 | PASS | Verified starting inventory of one branch (`main`) and zero pull requests. Direct publication and final inventory are checked against GitHub. |
| A20 | PASS | Scope is synthetic. Native qualification and the paired resource study remain open. |

The Stage 1.3 five-pair plan and all historical authorization values remain frozen. The fixture-owner loss case preserves its unobserved pipe outcomes. The forced-subject case preserves its provider-facing observation gaps separately from successful fixture cleanup.

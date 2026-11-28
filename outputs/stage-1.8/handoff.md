# Stage 1.8 independent witness and controller recovery

The independent Windows witness survived all four real controller terminations, detected closure and exit through its own handles, and settled the guard and both target jobs. Each fault journal finalized as **incomplete** with fixture EOF unavailable. The normal case validated the exact synthetic request, response and clean fixture EOF as **observed success**. [Evidence](evidence.json) · [Architecture](architecture.md).

| Case | Verified checkpoint and outcome |
|---|---|
| Normal | Exact Stage 1.2 response through unchanged Stage 1.6 actors. All controller and actor exits at 0. Fixture input EOF, fixture-output terminal read and all three final job counts verified. |
| Before launch | Witness was ready. The controller exited 93 before any synthetic actor was started. Both target jobs had zero total and active processes. |
| Actors verified | The owner, server, root and relay identities and actual job memberships were observed before controller exit 93. Guard recovery settled the entire owned tree. |
| In flight | The request reached the relay's split write. The fixture gate held delivery. The controller exited 93, and response and terminal actor observations remained unavailable. |
| Response verified | The exact fixed response was recorded before controller exit 93. Neither normal fixture writer closure nor EOF was observed before recovery. |

The baseline was `59978aae05bd062e9ab93a4dea56a9498a88845f`. The accepted WPAI Constitution was v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9`. The Stage 1.7 matrix and the five-pair plan matched their frozen hashes. **Zero provider executables, sessions, API calls or account operations ran. `authorized_now` is `0`. Codex CLI 0.166.0, Antigravity CLI 1.5.18 and Grok Build 1.0.92 remain NO-GO.**

| ID | State | Evidence |
|---|---|---|
| A01 | PASS | Exact live project and canonical baselines verified. |
| A02 | PASS | Frozen Stage 1.7 matrix verified, including zero authorization and all three NO-GO decisions. |
| A03 | PASS | Local synthetic actors and public fixture only. No live provider actions or account changes. |
| A04 | PASS | Witness and controller ran as distinct Windows processes with independent retained identities. |
| A05 | PASS | Witness readiness preceded controller startup and every synthetic actor startup gate. |
| A06 | PASS | The witness created and held the exclusive durable journal writer. |
| A07 | PASS | Controller write opens to the protected canary and journal were denied. |
| A08 | PASS | Actual granted witness access was query on both target jobs and query plus terminate on the guard. |
| A09 | PASS | Real controller exit 93 was injected in each separate fault case. |
| A10 | PASS | Witness observed the actual controller terminal pipe read, retained signal and exit independently. |
| A11 | PASS | Three scoped jobs emptied within the 8,000 ms deadline in each loss case. Exact reference timings are included. |
| A12 | PASS | Actual retained exit codes, checkpoint memberships and final accounting recorded. |
| A13 | PASS | Controller loss preserved missing actor observations as unavailable. No fault journal reported fixture EOF. |
| A14 | PASS | Normal control verified the complete synthetic transaction, causal shutdown and real exits. |
| A15 | PASS | Strict hash chain, schema, ordering and mutation controls passed, including unscripted controller-loss recovery. |
| A16 | PASS | Verified 123 frozen historical source and evidence files against the starting bytes. [Historical inventory](historical.sha256) |
| A17 | PASS | Offline replay reproduced stable evidence and the publication manifest. [Manifest](manifest.sha256) |
| A18 | PENDING | Exact hosted implementation evidence is recorded after both Windows jobs pass. |
| A19 | PENDING | The closeout SHA has a separate hosted verification gate. |
| A20 | PASS | Exact starting inventory was only `main` with zero pull requests. Native NO-GO is unchanged. |

Local Windows checks ran with warnings treated as errors on Python 3.10.11 and 3.14.3. Remaining scope limits include native provider isolation and lifecycle, witness loss, power loss, kernel failure and arbitrary OS failure.

# Stage 1.7 provider account-state isolation

**All three pinned native routes remain NO-GO.** The matrix distinguishes pin-matched source from current documentation and records the evidence needed to reconsider each route. Zero provider executables or sessions ran, no provider API or account operation occurred, and `authorized_now` remains `0`. Native qualification and the paired study remain unauthorized. [Isolation matrix](isolation-matrix.json) · [Route assessment](route-assessment.md) · [Future director decisions](future-preflight-decisions.md).

| Route | Isolation finding | Unresolved prerequisite |
|---|---|---|
| Codex CLI 0.166.0 | `PARTIAL_ISOLATION` | Process-memory storage is version-matched. A fresh CLI has no persistent fallback. The existing subscription requires an authorized handoff that protects the ordinary credential store and provider-side session state. |
| Antigravity CLI 1.5.18 | `UNKNOWN` | Exact Windows keyring namespace, token writeback, global/user policy merge and worker sharing are unresolved. |
| Grok Build 1.0.92, build `b06756fd6256` | `PARTIAL_ISOLATION` | Historical scratch settings relied on an ordinary account reference. Exact pinned refresh and configuration precedence are unresolved, and the historical control recorded an extra tool. |

The project baseline was `948d7692d4787a6f04e853177e5ff3f11c7c7efb`. The canonical Constitution was v6.24.0 at `0adf5ecee5f7f96ce3749944dc097a003731a6e9`. The static matrix contains **23 version-matched source claims, 0 version-matched official-document claims and 12 current-only documentation claims**, plus 5 archival observations, 3 inferences and 5 explicit unknowns. Counts refer to catalog claims. Five pairs per route and the prior conditional study totals of 20 and 30 are frozen. The six separately proposed lifecycle cases remain hypothetical.

| ID | State | Evidence |
|---|---|---|
| A01 | PASS | Live project and canonical Constitution baselines verified before edits. |
| A02 | PASS | Exact historical versions, executable names and fingerprints copied from the frozen Stage 1.5 matrix. |
| A03 | PASS | Exact Codex storage analyzed from pinned source. Missing implementation boundaries explicitly recorded for the Antigravity and Grok routes. |
| A04 | PASS | Subscription, API-key, OAuth, external input and MCP credential domains distinguished. |
| A05 | PASS | Windows logon credential sets and client entry namespacing assessed without an OS store inspection. |
| A06 | PASS | State roots, storage overrides and configuration ordering mapped where proven, with exact gaps preserved. |
| A07 | PASS | Managed authority, inherited configuration, imports, plugins, built-in tools and updater risks assessed. |
| A08 | PASS | Claim provenance and current-only context enforced by the static validator. |
| A09 | PASS | Unmatched artifacts, historical checks and rolling docs do not clear isolation gates. |
| A10 | PASS | Each native route has its own isolation classification and NO-GO decision. |
| A11 | PASS | Exact proof requirements and separate director approval points are recorded. |
| A12 | PASS | Stage 1.3 and Stage 1.5 budgets and authorization confirmed by frozen hashes and value checks. |
| A13 | PASS | Zero provider executable starts, sessions, API usage and account or provider configuration changes. |
| A14 | PASS | 111 protected historical source and evidence files matched baseline bytes. [Historical inventory](historical.sha256) |
| A15 | PASS | Deterministic matrix and publication manifest verified offline. [Stage manifest](manifest.sha256) |
| A16 | PASS | Prior and new checks passed locally on Python 3.10.11 and 3.14.3 with warnings as errors. |
| A17 | PASS | The hosted implementation run passed both jobs against the exact implementation SHA. |
| A18 | EXTERNAL CHECK | The final publication report identifies and verifies the independent closeout run against its own SHA. |
| A19 | PASS | Starting inventory was only `main` with zero pull requests. Publication target is direct `main`. |
| A20 | PASS | Future decision records identify provider-specific gaps without granting new authority. |

## Hosted verification

GitHub Actions **Windows tests** run `46044601450` was triggered by a push to `main` at head `02628a19dc786bf406fe2f18248ede958daa4bcf` and concluded `success`. Both **Python 3.10.11** and **Python 3.14.3** passed Stage 1.7 static provider account-state isolation and every preceding verification step. [Hosted implementation run](https://github.com/MrWizard94-Compile/WPAI-Shared-Execution-Framework/actions/runs/46044601450)

The closeout changes this handoff and its manifest checksum. Its push triggers a separate Windows workflow run.

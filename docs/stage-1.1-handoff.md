# Stage 1.1 handoff

Stage 1.1 hardens `repo_health_v1` in `wpai-exec` 0.1.1. The product still has one read-only operation, one fixed allowlisted target and one local stdio server. The data contract remains `wpai.repo_health.v1`.

## Starting point and build

- Clean local `main` and live `origin/main` started at `dea5e311872b9fd2b0bbe021ba8e91547d365147`. Direct publication to the existing `main` was authorized. The canonical Constitution v6.24.0 and installed loader matched `0adf5ecee5f7f96ce3749944dc097a003731a6e9`. Stage 1.1 excludes constitutional amendments.
- Local Python 3.10.11 and 3.14.3 each passed **21 tests** with `-W error`. The same 21 tests passed again under both versions from the independently extracted package.
- Two fresh ZIP builds, one per Python version, were byte-identical. All six manifested files matched their source bytes. ZIP SHA-256 is `9063cd629145fee025a6330dd969a6bb608bc2571cca72dde5860947652a3686`. [Stage 1.1 package](../outputs/wpai-exec-stage-1.1.zip).
- The extracted Windows CLI returned all 12 observed W1 fields. A separate local HEAD read agreed and the before and after Git metadata fingerprints matched. From separate extracted stdio processes, each MCP revision completed discovery and denial with text/structured parity, then exited with code 0 on stdin EOF. Those smoke tests used local GitHub read authorization only for the CLI invocation.
- The workflow passed local YAML and semantics checks. Both official actions were verified against their signed tagged commits and pinned by full SHA. The runner is `windows-2025`, checkout uses `contents: read` with credentials persistence disabled, and the tests use synthetic inputs with no application credentials. The hosted run is recorded by GitHub for the publication commit. [Windows tests](https://github.com/MrWizard94-Compile/WPAI-Shared-Execution-Framework/actions/workflows/tests.yml).

## Runtime and protocol changes

Worker state is cleared in an identity-checked `finally` under the state lock. The acquisition path catches ordinary exceptions at the result boundary and returns a generic `UNAVAILABLE` payload. A result encoding failure produces a fixed JSON-RPC error. There is one acquisition worker. Separate input and bounded output handling prevents a stalled peer from holding the acquisition lock. Cancellation stops active acquisition and discards queued tool results that have yet to begin writing. EOF and broken stdout cancel active work and close the session. Tests exercise both simulated faults and real Windows pipes.

The catalog describes local Git and authenticated remote GitHub reads. Existing source and target fields identify metadata provenance. Display normalization removes terminal escapes and control or directionality formatting from repository text while preserving result fields and existing size limits. The operation uses original identifiers internally. The source label and display controls are guidance for downstream clients, which must treat metadata as untrusted evidence.

| Revision | Observed behavior |
|---|---|
| `2025-06-18` | Typed initialize identity and capabilities, `notifications/initialized`, legacy ping, deterministic discovery, correlated errors and text/structured tool output. |
| `2025-11-25` | Same handshake and operation behavior. The server offers this revision when an unsupported legacy revision is requested. |
| `2026-07-28` | Stateless discovery or direct request, required per-request version and capabilities, optional client identity, private zero-TTL cache metadata on discovery and list, `complete` tool results, and optional recommended server identity inside each successful result’s `_meta`. An unsupported modern version returns `-32022` and supported versions. Cancellation with just `requestId` is supported. |

Representative responses were independently validated against all three complete upstream JSON schemas. Offline tests assert required result fields projected from those schemas and exercise sequencing, cancellation, errors, parity, limits and EOF. In June 2025 mode, uncorrelatable malformed frames use the base JSON-RPC null ID because there is no valid request ID to echo. Later schemas permit an omitted error ID. These are stdio protocol and local process checks. Stage 1.1 does not supply new model-driven client compatibility evidence. The stdlib adapter is sufficient for this bounded operation. Revisit the SDK decision before implementing extensions or new transports. [Normative references and baseline protocol findings](stage-1.1-protocol.md).

## Publication and remaining limits

The publication review identified existing workstation details, paths and trace identifiers, and private-project operational metadata. No plausible active credential was found in the scoped review. Historical evidence was preserved, and the separate redacted-release proposal was left for a later authorization. [Publication review](stage-1.1-publication-review.md) · [Redacted release proposal](stage-1.1-redacted-release-plan.md).

GitHub results remain bounded snapshots and can be incomplete. CLI and client executables and their launch environment are trusted. Display filtering does not neutralize arbitrary natural language. A response whose write already started can race with cancellation or closure. The server depends on cooperative acquisition and OS-level subprocess behavior. The active Claude Code exception remains deferred. A next milestone could run the same operation against an approved synthetic fixture through the native client routes, keeping the current catalog and operation boundaries.

## Files changed

| File | Change |
|---|---|
| `README.md` | Updated setup, release links, and result trust boundary. |
| `work/wpai-exec/README.md` | Added lifecycle, scope, consumer guidance, test and build commands. |
| `work/wpai-exec/wpai_exec.py` | Hardened worker cleanup, per-era protocol behavior, and stdio cancellation and closure. |
| `work/wpai-exec/repo_health.py` | Added display-only repository text filtering. |
| `work/wpai-exec/tests/test_repo_health.py` | Added metadata and provenance regressions. |
| `work/wpai-exec/tests/test_stdio.py` | Added schema-derived wire, failure, recovery and real pipe regressions. |
| `.github/workflows/tests.yml` | Added least-privilege Windows tests for both Python versions. |
| `work/wpai-exec/build_package.py` | Added deterministic ZIP and manifest generation. |
| `outputs/wpai-exec-stage-1.1.zip` | Added the hardened, verified distribution. |
| `docs/stage-1.1-*.md` | Recorded findings, protocol audit, handoff and separate proposal. |

## Acceptance

| ID | Status | Evidence |
|---|---|---|
| A01 | PASS | Canonical accepted ref, 23 frozen files, loader and project instructions verified. |
| A02 | PASS | Starting tree was clean. No unauthorized repository changes. Read-only private CLI smoke verified unchanged Git metadata. |
| A03 | PASS | Normal, exceptional, cancelled, failed-output and EOF paths release acquisition state. |
| A04 | PASS | Generic `UNAVAILABLE` and encoding error contain no internal diagnostic text. |
| A05 | PASS | Recovery, concurrent denial, queued cancellation, EOF, and both sides of pipe backpressure tested. |
| A06 | PASS | Catalog declares local Git and authenticated read-only GitHub access. |
| A07 | PASS | Display normalization and source provenance verified with synthetic repository text. |
| A08 | PASS | `wpai.repo_health.v1` and output fields retained. Formatting changes are documented. |
| A09 | PASS | Both legacy revisions tested, including unsupported-version fallback. |
| A10 | PASS | Modern regression suite and representative full-schema validation passed. |
| A11 | PASS | Required version/capability fields, optional identity, cache placement and result behavior documented. |
| A12 | PASS | JSON text and structured payloads agree across all revisions. |
| A13 | PASS | Python 3.10.11 passed 21 tests with warnings as errors. |
| A14 | PASS | Python 3.14.3 passed 21 tests with warnings as errors. |
| A15 | PASS | Windows Actions workflow added. Local YAML, pins, matrix, permissions and exact unittest entry point verified. |
| A16 | PASS | Baseline public tree, history, nested archives and records audited. Findings and proposal documented. |
| A17 | PASS | Stage 0 records and both historical archives retain their Git blob bytes. |
| A18 | PASS | Builds from both runtimes match byte for byte. |
| A19 | PASS | Clean extraction, manifest, tests, live CLI and three stdio smoke routes verified. |
| A20 | PASS | Root and package docs match the built server and practice. |
| A21 | PASS | Candidate changes confined to existing `main` in the framework repository. |
| A22 | PASS | Candidate review covered exact staged blobs and nested archive members. No newly introduced sensitive values or unrelated artifacts identified. |
| A23 | PASS | Measurement, compatibility, platform and publication limits recorded here and in the review. |

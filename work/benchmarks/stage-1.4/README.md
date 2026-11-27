# Stage 1.4 independent Windows lifecycle witness

Run from the repository root on Windows with Python 3.10.11 or 3.14.3. The witness runs only the fixed offline synthetic scenarios.

```powershell
py -3.10 -B -W error -m unittest discover -s work/benchmarks/stage-1.4/tests -v
py -3.10 -B -W error work/benchmarks/stage-1.4/public_evidence.py
py -3.10 -B -W error work/benchmarks/stage-1.4/observer.py external_tree --record external-tree.jsonl
py -3.10 -B -W error work/benchmarks/stage-1.4/witness_record.py external-tree.jsonl
```

Use a new destination for each private ledger. The `external_tree` case starts the unchanged Stage 1.3.1 wrapper with its pinned fake MCP server. The observer waits for the initialization reply, retains both process handles, and requests termination from a separate process with a termination-only target Job Object handle. The observer stays outside the target job and records its own finalization after both subjects exit and the job empties. Validation exits zero for structurally complete `observed_success` and `observed_failure` records. Read the status to distinguish a clean lifecycle from a witnessed failure. The other statuses exit nonzero.

The `observer_crash` scenario deliberately exits the observer process. The qualification suite runs that scenario in a separate guard Job Object and verifies that the guard becomes empty. The validator checks the incomplete ledger afterward.

## Witness record v1

Each JSONL line contains `schema` (`wpai.benchmark.lifecycle-witness.v1`), `run_id`, `seq`, elapsed `monotonic_ns`, `kind`, typed `data`, `previous` and `sha256`. The first link is 64 zeroes. SHA-256 covers the canonical sorted compact JSON of all other fields. Each line is flushed and synced before the next, with limits of 96 events and 2,048 bytes per line. The file is created exclusively with read sharing, and only the observer owns its writer. The record contains run-scoped process and creation tokens, enumerated facts, and limited numeric exit and I/O codes. It omits real PIDs, local paths, environment data, arguments, and protocol payloads.

| Event | Meaning |
|---|---|
| `observer_started`, `observer_finalized` | Before and after identities and checked target-job separation. A partial ledger remains incomplete. |
| `process_registered` | Retained process identity, creation identity, source and membership. |
| `handle_signaled`, `process_exit`, `process_active` | Independent Windows wait and exit-code results. A still-active server or descendant can be observed after wrapper exit. |
| `stdin_writer_closed`, `fixture_marker` | The observer closed its writer and the trusted synthetic actor independently reported an empty stdin read and output completion over a dedicated pipe. |
| `pipe_terminal` | Direct kernel result on an owned read endpoint or the observer closing its own reader. |
| `job_accounting` | Active and total target Job Object counts at named points. |
| `force_requested`, `owner_acknowledged`, `receipt_checked` | Termination request, owner acknowledgment and independent check for a v2 in-band receipt. |
| `issue` | Bounded invalid, unavailable or failure reason. |

The validator reports `observed_success`, `observed_failure`, `unavailable`, `invalid` or `incomplete`. A clean record requires registered and signaled processes with actual zero exit codes, confirmed EOF on both synthetic routes, verified job emptiness, and a complete observer record. The synthetic actor attestation is scoped to the test peer. Kernel pipe closure under forced termination does not establish application EOF, and the observer cannot read the real wrapper's private inner server pipes.

`public_evidence.py --write` recreates the normalized Stage 1.4 evidence and SHA-256 inventory from live synthetic replays. Normalization removes per-run identities, time and incidental event order after validating the original chain. The private raw ledger is the source for event order. The published normalized evidence is compared by byte on both Python versions. [Architecture and limitations](../../../outputs/stage-1.4/architecture.md) · [Handoff](../../../outputs/stage-1.4/handoff.md)

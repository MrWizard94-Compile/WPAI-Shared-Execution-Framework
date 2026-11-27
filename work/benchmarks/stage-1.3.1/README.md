# Stage 1.3.1 offline corrective tools

These entry points supersede Stage 1.3 for new lifecycle receipts and future pair analysis. The [Stage 1.3 tools](../stage-1.3/) reproduce the archived result and the original five-pair plan.

Run from the repository root on Windows with Python 3.10.11 or 3.14.3. Substitute either pinned version in the commands below.

```powershell
py -3.10 -B -W error -m unittest discover -s work/benchmarks/stage-1.3.1/tests -v
py -3.10 -B -W error work/benchmarks/stage-1.3.1/public_evidence.py
py -3.10 -B -W error work/benchmarks/stage-1.3.1/comparator.py
```

`public_evidence.py --write` regenerates the versioned Stage 1.3.1 verification JSON. The comparator emits reconciliation v2. Each client event or trace collection has an explicit status and a numeric count only when observed. Omitted and null inputs are `unavailable`. Wrong container types or malformed members are `invalid`. A valid empty collection is `observed` with count zero. A valid nonmatching event contributes to the collection count and contributes zero expected matches. Tool starts, completions, server responses, final answer and lifecycle have separate gates.

## Lifecycle receipt and merge

Start `wrapper.py treatment --record <new-receipt.json> --run-id <id>` through a local synthetic stdio harness. Both arms are supported. Use a unique opaque 32-digit lowercase hexadecimal ID per run. An offline harness may retain the ID the wrapper creates if the flag is omitted. The wrapper forwards protocol bytes on stdout and leaves diagnostics in the bounded optional private stderr file. Finish reading expected responses before closing input.

The `wpai.benchmark.lifecycle.v2` receipt binds the run ID, arm and frozen fixture identities. It reports integer `pump_threads_started` and `pump_threads_stopped`, boolean `pump_threads_verified_stopped`, and the `outstanding_pump_threads` list. The only pump names are `stdin`, `stdout` and `stderr`. All three must have terminated to verify transport. `transport_faults` records at most one entry per fault site. `transport_fault_winerrors` records the first nonzero native error for a reported fault site when available. A failed receipt can still be merged and inspected. A v1 receipt supplies no pump proof.

The supervisor sets the stop flag before attempting Windows cancellation. `ERROR_NOT_FOUND` means no synchronous operation was pending at that instant. The supervisor may try again during the bounded wait so it can catch I/O started just before shutdown. A successful request still requires confirmation that the thread stopped. Stream and thread handles owned by a pump remain with it until its I/O returns. At the deadline, an outstanding pump is named and the receipt fails transport and lifecycle validation. A process-tree cleanup result is reported independently. [Windows synchronous I/O cancellation](https://learn.microsoft.com/en-us/windows/win32/fileio/cancelsynchronousio-func)

Collect the normalized run under the same ID, arm and fixture identities. Attach the original standalone receipt as a JSON object under `lifecycle` in a new file.

```powershell
py -3.10 -B -W error work/benchmarks/stage-1.3.1/lifecycle_receipt.py run.json receipt.json --output merged-run.json
```

The merge verifies both inputs, rejects any existing `lifecycle` member, preserves the other run fields, and refuses to overwrite a file. The comparator checks the association and shutdown facts again. Preserve the source run and standalone receipt to establish provenance. `paired_stats.py <provider> <pairs.json>` uses these merged records in its control and treatment slots and applies the v2 gates. The Stage 1.3 schedule remains plan-only. [Stage 1.3.1 handoff](../../../outputs/stage-1.3.1/handoff.md)

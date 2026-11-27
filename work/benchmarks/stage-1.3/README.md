# Stage 1.3 offline benchmark tools

Run these commands from the repository root on Windows. Use either pinned version, Python 3.10.11 or 3.14.3. All code uses the standard library.

```powershell
py -3.10 -B -W error -m unittest discover -s work/benchmarks/stage-1.3/tests -v
py -3.14 -B -W error -m unittest discover -s work/benchmarks/stage-1.3/tests -v
py -3.10 -B -W error work/benchmarks/stage-1.3/public_evidence.py
py -3.14 -B -W error work/benchmarks/stage-1.3/public_evidence.py
py -3.10 -B -W error work/benchmarks/stage-1.3/plan.py --plan-only --seed 20261127
```

`plan.py` defaults to plan-only and reads the Stage 1.2 records. `public_evidence.py --write` regenerates the versioned Stage 1.3 JSON. `comparator.py` emits the reconciliation to stdout. The archived reduction fields reproduce the pilot using its archived observation criteria. The comparator's default analysis for future pairs requires complete run-bound lifecycle evidence and measured fixture identities for both arms.

For offline tests, `wrapper.py treatment --record <new-file>` starts the pinned synthetic fixture and uses binary stdin and stdout. The `control` arm is also supported. A test client should read the responses it expects, then close its input. The wrapper exits zero when the client closes stdin, the server reads EOF and exits zero, all owned processes are gone, and transport completes without faults or cancellation. The wrapper's exit code describes lifecycle. Verify the MCP payloads separately. The record contains sanitized counters and shutdown evidence. An optional `--private-stderr <new-file>` writes at most 4096 bytes of worker diagnostics. Keep that file out of public evidence. The wrapper takes an optional `--timeout` in seconds with a default of 60.

The child waits for a one-byte private startup handshake before loading fixture code. The supervisor assigns the child to a Windows Job Object with kill-on-close and no breakaway, then releases the handshake. The worker records its first empty stdin read through a private handle. The supervisor observes the Windows process exit code and counts remaining job members independently. Separate I/O pumps forward bytes unchanged, complete partial writes, and cancel blocked Windows synchronous I/O after bounded grace. An outer owner can kill the wrapper and prevent a record. The offline suite exercises this case with a synthetic outer job. [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) · [CancelSynchronousIo](https://learn.microsoft.com/en-us/windows/win32/fileio/cancelsynchronousio-func)

`paired_stats.py <provider> <pairs.json>` reads one provider's JSON array. Each object has a unique `pair_id` and embedded `control` and `treatment` raw run records in the Stage 1.2 normalized shape. Future run records also need a distinct `run_id` for each arm, measured `fixture_identities`, and the original `lifecycle` receipt from that run. Pass the opaque ID to the wrapper with `--run-id` or retain the one it generates. The comparator checks the receipt's ID, arm and fixture hashes against the run and its frozen inputs. Retain the source records so receipt provenance can be verified. Capture counters for each arm and preserve missing observations as null. The output includes per-pair differences, reduction fractions for positive control baselines, ranges, medians and missing counts. Eligibility is evaluated per metric. Provider groups stay separate.

The [handoff](../../../outputs/stage-1.3/handoff.md) carries the acceptance matrix and the future live authorization gate.

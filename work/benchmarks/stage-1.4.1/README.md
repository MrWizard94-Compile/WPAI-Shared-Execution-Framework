# Stage 1.4.1 strict witness qualification

Use `qualify_witness.py` as the acceptance command for every new synthetic witness ledger. It reads the frozen Stage 1.4 v1 serialization and evaluates the named scenario against its ordered observations. The archived Stage 1.4 parser remains useful for interpreting lifecycle status.

Run from the repository root on Windows with Python 3.10.11 or 3.14.3. Use a fresh path for the disposable ledger.

```powershell
py -3.10 -B -W error work/benchmarks/stage-1.4/observer.py external_tree --record external-tree.jsonl
py -3.10 -B -W error work/benchmarks/stage-1.4.1/qualify_witness.py external_tree external-tree.jsonl
py -3.10 -B -W error -m unittest discover -s work/benchmarks/stage-1.4.1/tests -v
py -3.10 -B -W error work/benchmarks/stage-1.4.1/verify_prior.py
py -3.10 -B -W error work/benchmarks/stage-1.4.1/public_evidence.py
```

The first command captures the evidence. The second is the qualification gate and exits zero only on `qualification: pass`. Specify the expected scenario explicitly. A passing negative case can still have `lifecycle_status: observed_failure`, `unavailable` or `invalid`. The separate `missing` and `conflicts` fields identify scenario requirements that lacked evidence or were contradicted. The `unobserved` field retains gaps in the underlying lifecycle evidence, including the inaccessible server endpoints in the external-owner scenario. An incomplete observer ledger exits nonzero, including the deliberate crash case.

| Scenario | Additional evidence checked |
|---|---|
| `external_tree` | External owner and matched job membership, request before acknowledgment, actual signals and exit codes, post-force wrapper peer closure, explicit absent receipt, final job counts, and outside observer finalization. |
| `wrapper_only` | Wrapper force and exit, surviving server, one active job member, subsequent cleanup and server exit. |
| `descendant` | Root exit, independently live descendant, two active members out of three, then descendant exit and empty job. |
| `local_pipe_close` | Direct server stdout local-close observation before cleanup, with no claimed graceful EOF. |
| Natural exits | Exact zero or nonzero code, actual terminal reads, trusted EOF markers and the specified shutdown order. |
| Other negative cases | Explicit broken control, missing registration or exit code, identity mismatch, or timeout evidence. A crash ledger remains incomplete. |

The previous manifest includes the shared workflow bytes. `verify_prior.py` reconstructs the exact Stage 1.4 workflow in a disposable local snapshot, verifies its original hash, and runs the original evidence verifier in that snapshot. `public_evidence.py --write` regenerates Stage 1.4.1 evidence from synthetic replays and renews the new manifest. The versioned verdicts omit run IDs and timestamps. [Handoff](../../../outputs/stage-1.4.1/handoff.md) · [Validation decision](../../../outputs/stage-1.4.1/validation.md)

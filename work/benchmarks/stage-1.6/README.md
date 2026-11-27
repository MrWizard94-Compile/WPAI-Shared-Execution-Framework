# Stage 1.6 offline reproduction

Run from the repository root on Windows with Python 3.10.11 or 3.14.3. The standard-library harness expects a local NTFS temporary directory that supports Windows integrity labels and an environment that permits newly created processes to join the harness's unnamed jobs. It stops if a job, handle, or scratch storage protection cannot be verified.

```powershell
python -B -W error -m unittest discover -s work/benchmarks/stage-1.6/tests -v
python -B -W error work/benchmarks/stage-1.6/public_evidence.py
```

The unit discovery command runs real Windows scenarios and rechained mutation tests. The evidence command reruns the four published cases, validates the raw ledgers, compares the normalized JSON, and verifies both SHA-256 inventories. None of the commands requires a provider executable, account, listener, or remote connection.

Use `public_evidence.py --write` to regenerate the Stage 1.6 normalized evidence and manifest after an intentional edit. The historical inventory is anchored to Git blobs from the frozen baseline. The harness uses only a new temporary directory. It keeps raw evidence there until validated and publishes only fixed event summaries.

[Handoff and acceptance](../../../outputs/stage-1.6/handoff.md) · [Topology and witness contract](../../../outputs/stage-1.6/architecture.md)

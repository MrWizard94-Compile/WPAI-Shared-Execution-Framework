# Stage 1.8 offline Windows reproduction

Run from the repository root on Windows with Python 3.10.11 or 3.14.3 and a disposable NTFS temporary directory. The harness needs nested, unnamed Windows Job Objects, low-integrity process tokens and local mandatory integrity labels.

```powershell
python -B -W error -m unittest discover -s work/benchmarks/stage-1.8/tests -v
python -B -W error work/benchmarks/stage-1.8/public_evidence.py
```

The unit discovery command uses fresh real Windows processes and checks rechained evidence mutations. The evidence verifier verifies the protected history, runs the five published scenarios, compares the normalized result and checks the Stage 1.8 SHA-256 manifest.

Use the evidence verifier with `--write` to reproduce the evidence and manifest while keeping the measured reference run. Use `--capture` when intentionally replacing the reference measurement with a new run. Actual scheduling and exit timing can vary, so the verifier checks the fixed causal outcome and deadline on every replay and preserves the archived numeric observations for byte-for-byte comparison.

The harness reads the approved synthetic fixture and dataset from this checkout. It uses fixed Python entry points and anonymous pipes. Provider executables, credentials, network access and an ordinary project workspace are unnecessary.

[Architecture and evidence contract](../../../outputs/stage-1.8/architecture.md) · [Handoff](../../../outputs/stage-1.8/handoff.md)

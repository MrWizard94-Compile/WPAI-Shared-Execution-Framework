# Stage 1.7 offline reproduction

Run from the repository root with Python 3.10.11 or 3.14.3.

```powershell
python -B -W error -m unittest discover -s work/benchmarks/stage-1.7/tests -v
python -B -W error work/benchmarks/stage-1.7/public_evidence.py
```

The standard-library verifier reads the prior frozen matrices, reproduces `isolation-matrix.json` from the catalog, validates the versioned schema and source applicability, and compares both SHA-256 inventories. It uses the Stage 1.5 generic schema evaluator and runs without network access, account access or provider processes.

After an intentional catalog or document change, the evidence verifier's `--write` option regenerates the new matrix and package manifest. Review the exact diff and rerun the checks. The historical inventory is an input anchored to the frozen baseline.

[Stage handoff](../../../outputs/stage-1.7/handoff.md) · [Route assessment](../../../outputs/stage-1.7/route-assessment.md)

# Stage 1.5 offline reproduction

From the repository root on either Windows CI Python version, 3.10.11 or 3.14.3:

```powershell
python -B -W error -m unittest discover -s work/benchmarks/stage-1.5/tests -v
python -B -W error work/benchmarks/stage-1.5/public_evidence.py
```

The standard-library validator regenerates the route matrix from the static catalog, checks it against the versioned schema, verifies historical client versions and the frozen repeatability plan, and checks both SHA-256 manifests. The history inventory covers the source and evidence directories for Stages 1.2 through 1.4.1. Its pinned digest comes from the baseline Git blobs, so verification works in the hosted shallow checkout. The Stage 1.5 manifest covers the new source, tests and outputs except the manifest itself.

To regenerate the matrix and Stage 1.5 manifest after an intentional assessment edit, run the evidence verifier with `--write`, review the diff, then run both commands above. The frozen historical hash list is an input. Neither verification nor regeneration runs a provider, queries the network, contacts authentication, or changes authorization.

[Published handoff](../../../outputs/stage-1.5/handoff.md)

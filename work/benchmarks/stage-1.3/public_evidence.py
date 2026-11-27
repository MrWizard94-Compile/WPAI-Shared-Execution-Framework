"""Regenerate or verify the deterministic Stage 1.3 public JSON records."""

import argparse
import json

from comparator import report
from evidence import ROOT, ROUTES, TOOLS
from plan import make_plan


DESTINATION = ROOT / "outputs" / "stage-1.3"


def usage_reference(reconciliation):
    return {
        "schema": "wpai.benchmark.usage-reference.v1",
        "scope": "Selected Stage 1.2 subscription pilot observations by provider and arm.",
        "interpretation": ("No future spend, quota or latency guarantee. Grok USD fields are client telemetry. "
                           "Actual billed API charges and attributable quota changes were unavailable."),
        "providers": {
            provider: {
                "description": reconciliation["providers"][provider]["control"]["usage_definition"],
                "stage_1_2_pair_eligible": reconciliation["providers"][provider]["pair_eligible"],
                "stage_1_3_resource_metrics_eligible": reconciliation["providers"][provider]["resource_metrics_eligible"],
                "arms": {
                    arm: reconciliation["providers"][provider][arm]["metrics"] for arm in TOOLS
                },
            } for provider in ROUTES
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write the three versioned artifacts")
    args = parser.parse_args()
    reconciliation = report()
    artifacts = {"reconciliation.json": reconciliation, "repeatability-plan.json": make_plan(),
                 "usage-reference.json": usage_reference(reconciliation)}
    if args.write:
        DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, artifact in artifacts.items():
        path = DESTINATION / name
        data = (json.dumps(artifact, indent=2, allow_nan=False) + "\n").encode()
        if args.write:
            path.write_bytes(data)
        elif path.read_bytes() != data:
            raise SystemExit(f"Versioned evidence differs from regenerated {name}")
    print("Verified deterministic Stage 1.3 JSON evidence.")


if __name__ == "__main__":
    main()

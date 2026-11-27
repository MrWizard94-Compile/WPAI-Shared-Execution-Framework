"""Describe one provider's paired measurements from a JSON array of raw run pairs."""

import argparse
import json
from pathlib import Path
from statistics import median

from comparator import RESOURCE_METRICS, TOOL_METRICS, compare_pair
from evidence import ROUTES, SOURCE, is_run_id, number, read, text_value, verify_inputs


def distribution(values):
    if not values:
        return {"count": 0, "median": None, "minimum": None, "maximum": None}
    return {"count": len(values), "median": median(values), "minimum": min(values), "maximum": max(values)}


def describe_metric(pairs, metric):
    observations = []
    for pair_id, pair in pairs.items():
        control, treatment = (number(pair[arm]["metrics"].get(metric)) for arm in ("control", "treatment"))
        eligible = pair["metric_eligibility"].get(metric) is True and control is not None and treatment is not None
        difference = control - treatment if eligible else None
        fraction = difference / control if eligible and control > 0 else None
        observations.append({"pair_id": pair_id, "eligible": eligible, "control": control, "treatment": treatment,
                             "difference_control_minus_treatment": difference, "reduction_fraction": fraction})

    return {
        "pairs": observations,
        "missing_control": sum(row["control"] is None for row in observations),
        "missing_treatment": sum(row["treatment"] is None for row in observations),
        "pairs_missing_either": sum(row["control"] is None or row["treatment"] is None for row in observations),
        "present_but_ineligible": sum(row["control"] is not None and row["treatment"] is not None
                                      and not row["eligible"] for row in observations),
        "eligible_zero_denominator": sum(row["eligible"] and row["control"] == 0 for row in observations),
        "distributions": {key: distribution([row[key] for row in observations if row["eligible"] and row[key] is not None])
                          for key in ("control", "treatment", "difference_control_minus_treatment", "reduction_fraction")},
    }


def summarize(provider, records, oracle):
    if provider not in ROUTES or not isinstance(records, list) or not records:
        raise ValueError("Expected a supported provider and at least one pair")
    compared = {}
    seen_runs = set()
    for item in records:
        pair_id = text_value(item.get("pair_id"))
        if not pair_id or pair_id in compared or any(item[arm].get("provider") != provider for arm in ("control", "treatment")):
            raise ValueError("Each pair needs a unique ID and both runs must belong to the selected provider")
        for arm in ("control", "treatment"):
            run_id = item[arm].get("run_id")
            if is_run_id(run_id):
                if run_id in seen_runs:
                    raise ValueError("A run cannot appear more than once in the paired sample")
                seen_runs.add(run_id)
        compared[pair_id] = compare_pair(item["control"], item["treatment"], oracle)
    return {
        "schema": "wpai.benchmark.paired-description.v1", "provider": provider, "pair_count": len(compared),
        "interpretation": "Descriptive results for this set of pairs. Positive differences favor treatment for these counts.",
        "metrics": {name: describe_metric(compared, name) for name in (*TOOL_METRICS, *RESOURCE_METRICS)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=ROUTES)
    parser.add_argument("pairs", type=Path)
    args = parser.parse_args()
    verify_inputs()
    result = summarize(args.provider, read(args.pairs), read(SOURCE / "ground_truth.json"))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

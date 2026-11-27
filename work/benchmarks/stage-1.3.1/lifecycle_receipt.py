"""Validate and attach a standalone lifecycle receipt to one normalized run."""

import argparse
import json
from pathlib import Path
import sys


# Reuse the frozen fixture identities and strict JSON decoder from Stage 1.3.
sys.path.append(str(Path(__file__).resolve().parents[1] / "stage-1.3"))
from evidence import IDENTITIES, TOOLS, is_run_id, number, read


SCHEMA = "wpai.benchmark.lifecycle.v2"
PUMP_NAMES = ("stdin", "stdout", "stderr")
BOOLEAN_FIELDS = ("client_stdin_eof", "child_stdin_closed", "server_eof_observed", "forced_termination",
                  "process_tree_verified_gone", "pump_threads_verified_stopped", "transport_ok", "lifecycle_valid")


def validate_association(run, receipt):
    if not isinstance(run, dict) or not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError("Expected a normalized run object and a v2 lifecycle receipt")
    run_id = run.get("run_id")
    if not is_run_id(run_id) or receipt.get("run_id") != run_id:
        raise ValueError("Lifecycle receipt run ID mismatch")
    arm = run.get("arm")
    if not isinstance(arm, str) or arm not in TOOLS or receipt.get("arm") != arm:
        raise ValueError("Lifecycle receipt arm mismatch")
    if run.get("fixture_identities") != IDENTITIES or receipt.get("fixture_identities") != IDENTITIES:
        raise ValueError("Lifecycle receipt fixture identity mismatch")

    if any(type(receipt.get(field)) is not bool for field in BOOLEAN_FIELDS):
        raise ValueError("Malformed lifecycle flags")
    for field in ("server_exit_code", "active_processes_at_check", "processes_in_owned_job"):
        if field not in receipt or (receipt[field] is not None and number(receipt[field], integer=True) is None):
            raise ValueError("Malformed lifecycle process evidence")
    started = number(receipt.get("pump_threads_started"), integer=True)
    stopped = number(receipt.get("pump_threads_stopped"), integer=True)
    outstanding = receipt.get("outstanding_pump_threads")
    if (started is None or stopped is None or not 0 <= stopped <= started <= len(PUMP_NAMES)
            or not isinstance(outstanding, list)
            or any(name not in PUMP_NAMES for name in outstanding)
            or len(set(outstanding)) != len(outstanding) or len(outstanding) != started - stopped):
        raise ValueError("Inconsistent lifecycle pump counts or identities")
    if receipt["pump_threads_verified_stopped"] != (started == stopped == len(PUMP_NAMES)):
        raise ValueError("Inconsistent lifecycle pump verification flag")
    faults = receipt.get("transport_faults")
    if not isinstance(faults, list) or any(not isinstance(fault, str) or not fault for fault in faults):
        raise ValueError("Malformed lifecycle transport faults")
    winerrors = receipt.get("transport_fault_winerrors")
    if (not isinstance(winerrors, dict) or
            any(name not in faults or type(code) is not int or code <= 0 for name, code in winerrors.items())):
        raise ValueError("Inconsistent lifecycle Windows fault codes")
    if receipt["transport_ok"] != (receipt["pump_threads_verified_stopped"] and not faults):
        raise ValueError("Inconsistent lifecycle transport flag")
    reason = receipt.get("termination_reason")
    if not isinstance(reason, str) or not reason:
        raise ValueError("Missing lifecycle termination reason")


def clean_lifecycle(receipt):
    """Evaluate validated v2 facts independently of the receipt's summary flag."""
    return (receipt["client_stdin_eof"] and receipt["child_stdin_closed"] and receipt["server_eof_observed"]
            and receipt["server_exit_code"] == 0 and not receipt["forced_termination"]
            and receipt["process_tree_verified_gone"] and receipt["active_processes_at_check"] == 0
            and (receipt["processes_in_owned_job"] or 0) > 0
            and receipt["pump_threads_verified_stopped"] and receipt["transport_ok"]
            and receipt["termination_reason"] == "child_exited")


def merge_receipt(run, receipt):
    if isinstance(run, dict) and "lifecycle" in run:
        raise ValueError("Normalized run already has a lifecycle member")
    validate_association(run, receipt)
    if receipt["lifecycle_valid"] != clean_lifecycle(receipt):
        raise ValueError("Inconsistent lifecycle outcome")
    return {**run, "lifecycle": receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        merged = merge_receipt(read(args.run), read(args.receipt))
        encoded = json.dumps(merged, indent=2, allow_nan=False) + "\n"
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(encoded)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()

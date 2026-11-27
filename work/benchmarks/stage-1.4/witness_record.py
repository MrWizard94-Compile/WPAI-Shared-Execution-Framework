"""Write and validate the bounded Stage 1.4 evidence ledger."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time


SCHEMA = "wpai.benchmark.lifecycle-witness.v1"
MAX_EVENTS = 96
MAX_LINE = 2048
GENESIS = "0" * 64
ROLES = ("wrapper", "server", "descendant", "owner")
CHANNELS = ("wrapper_stdout", "server_stdout", "wrapper_control", "server_control", "owner_control")
SCENARIOS = ("normal", "server_zero", "server_nonzero", "wrapper_only", "external_tree", "descendant",
             "local_pipe_close", "channel_broken", "observer_crash", "missing_registration", "missing_exit",
             "identity_mismatch", "timeout")
OBSERVATIONS = {
    "observer_started": ("scenario", "identity", "created", "outside_job"),
    "process_registered": ("role", "identity", "created", "in_job", "source"),
    "handle_signaled": ("role", "source"),
    "process_exit": ("role", "code", "source"),
    "process_active": ("role", "checkpoint", "source"),
    "pipe_terminal": ("channel", "outcome", "winerror", "source"),
    "stdin_writer_closed": ("role", "source"),
    "fixture_marker": ("role", "marker", "source"),
    "job_accounting": ("checkpoint", "total", "active", "source"),
    "force_requested": ("target", "source"),
    "owner_acknowledged": ("source",),
    "receipt_checked": ("present", "source"),
    "issue": ("class", "code"),
    "observer_finalized": ("identity", "outside_job", "source"),
}
ISSUES = {
    "invalid": {"identity_mismatch", "invalid_control_message", "unexpected_fixture_payload"},
    "unavailable": {"missing_registration", "missing_exit", "channel_disconnected", "observation_api_failed"},
    "failure": {"timeout"},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return sha256(data).hexdigest()


def token(value, digits=64):
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{digits}}}", value) is not None


def uint(value, limit=2**64):
    return type(value) is int and 0 <= value < limit


def valid_data(kind, data):
    if not isinstance(kind, str) or kind not in OBSERVATIONS or not isinstance(data, dict):
        return False
    if set(data) != set(OBSERVATIONS[kind]):
        return False
    if kind == "observer_started":
        return (data["scenario"] in SCENARIOS and token(data["identity"]) and token(data["created"])
                and type(data["outside_job"]) is bool)
    if kind == "process_registered":
        return (data["role"] in ROLES and token(data["identity"]) and token(data["created"])
                and type(data["in_job"]) is bool and data["source"] in ("created_handle", "bounded_job_membership"))
    if kind == "handle_signaled":
        return data["role"] in ROLES and data["source"] == "WaitForSingleObject"
    if kind == "process_exit":
        return data["role"] in ROLES and uint(data["code"], 2**32) and data["source"] == "GetExitCodeProcess"
    if kind == "process_active":
        return (data["role"] in ("server", "descendant") and data["checkpoint"] == "after_wrapper_exit"
                and data["source"] == "WaitForSingleObject")
    if kind == "pipe_terminal":
        if data["channel"] not in CHANNELS or not uint(data["winerror"], 2**32):
            return False
        outcome, error, source = data["outcome"], data["winerror"], data["source"]
        if outcome == "peer_closed":
            return source == "ReadFile" and error in (38, 109)
        if outcome == "local_close":
            return source == "observer_closed_reader" and error == 0
        if outcome in ("zero_read", "budget_exceeded"):
            return source == "ReadFile" and error == 0
        return outcome == "read_error" and source in ("PeekNamedPipe", "ReadFile") and error not in (0, 38, 109)
    if kind == "fixture_marker":
        return (data["role"] in ("wrapper", "server") and data["marker"] in ("stdin_eof", "stdout_finished")
                and data["source"] == "trusted_fixture_control_pipe")
    if kind == "stdin_writer_closed":
        return data["role"] in ("wrapper", "server") and data["source"] == "observer_closed_writer"
    if kind == "job_accounting":
        return (data["checkpoint"] in ("registered", "after_wrapper_exit", "final")
                and uint(data["active"], 9) and uint(data["total"], 9) and data["active"] <= data["total"]
                and data["source"] == "QueryInformationJobObject")
    if kind == "force_requested":
        return data["target"] in ("wrapper", "job", "owner") and data["source"] in ("observer_control", "external_owner")
    if kind == "owner_acknowledged":
        return data["source"] == "owner_control_pipe"
    if kind == "receipt_checked":
        return type(data["present"]) is bool and data["source"] == "observer_checked_legacy_receipt_path"
    if kind == "issue":
        return (isinstance(data["class"], str) and data["class"] in ISSUES
                and isinstance(data["code"], str) and data["code"] in ISSUES[data["class"]])
    return (token(data["identity"]) and type(data["outside_job"]) is bool
            and data["source"] == "observer_terminal_record")


class Ledger:
    def __init__(self, stream, run_id):
        if not token(run_id, 32):
            raise ValueError("Invalid run identity")
        self.stream = stream
        self.run_id = run_id
        self.start = time.monotonic_ns()
        self.previous = GENESIS
        self.count = 0
        self.finished = False

    def add(self, kind, **data):
        if self.finished or self.count >= MAX_EVENTS or not valid_data(kind, data):
            raise ValueError("Invalid or excessive witness observation")
        event = {"schema": SCHEMA, "run_id": self.run_id, "seq": self.count,
                 "monotonic_ns": time.monotonic_ns() - self.start, "kind": kind, "data": data,
                 "previous": self.previous}
        event["sha256"] = digest(canonical(event))
        line = canonical(event) + b"\n"
        if len(line) > MAX_LINE or self.stream.write(line) != len(line):
            raise OSError("Incomplete witness write")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.count += 1
        self.previous = event["sha256"]
        self.finished = kind == "observer_finalized"


def unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate witness field")
        data[key] = value
    return data


def read_events(path):
    events = []
    previous, elapsed = GENESIS, 0
    run_id = None
    with Path(path).open("rb") as stream:
        while line := stream.readline(MAX_LINE + 1):
            if len(line) > MAX_LINE or len(events) == MAX_EVENTS:
                raise ValueError("Witness ledger bound exceeded")
            if not line.endswith(b"\n"):
                if events and events[-1]["kind"] == "observer_finalized":
                    raise ValueError("Trailing bytes after finalization")
                return events, True
            event = json.loads(line, object_pairs_hook=unique_keys)
            if not isinstance(event, dict) or set(event) != {
                "schema", "run_id", "seq", "monotonic_ns", "kind", "data", "previous", "sha256",
            }:
                raise ValueError("Unexpected witness envelope")
            if canonical(event) + b"\n" != line:
                raise ValueError("Noncanonical witness record")
            checksum = event["sha256"]
            header = {key: value for key, value in event.items() if key != "sha256"}
            if (event["schema"] != SCHEMA or not token(event["run_id"], 32) or
                    (run_id is not None and event["run_id"] != run_id)
                    or not uint(event["seq"]) or event["seq"] != len(events)
                    or not uint(event["monotonic_ns"]) or event["monotonic_ns"] < elapsed
                    or event["previous"] != previous or checksum != digest(canonical(header))
                    or not valid_data(event["kind"], event["data"])):
                raise ValueError("Invalid witness content or chain")
            if events and events[-1]["kind"] == "observer_finalized":
                raise ValueError("Observation after finalization")
            run_id, previous, elapsed = event["run_id"], checksum, event["monotonic_ns"]
            events.append(event)
    return events, False


def summarize(events, unfinished_line=False):
    if not events:
        return {"status": "incomplete", "observer_finalized": False}
    if events[0]["kind"] != "observer_started":
        raise ValueError("Missing initial observer identity")
    start = events[0]["data"]
    registrations, terminals, exits, accounting, forces = {}, {}, {}, {}, {}
    terminal_order, force_order = {}, {}
    signaled, active_after_exit, markers, stdin_writers_closed = set(), set(), set(), set()
    issues = []
    finish, receipt, ack = None, None, False
    identities = {start["identity"]}
    creation_identities = {start["created"]}

    def once(target, key, value):
        if key in target:
            raise ValueError("Duplicate witness observation")
        target[key] = value

    for event in events[1:]:
        kind, data = event["kind"], event["data"]
        role = data.get("role")
        if kind == "process_registered":
            if (data["identity"] in identities or data["created"] in creation_identities
                    or data["in_job"] != (role != "owner")):
                raise ValueError("Duplicate identity or incorrect job membership")
            identities.add(data["identity"])
            creation_identities.add(data["created"])
            once(registrations, role, {"source": data["source"], "in_job": data["in_job"]})
        elif kind == "handle_signaled":
            if role not in registrations or role in signaled:
                raise ValueError("Signal without unique retained registration")
            signaled.add(role)
        elif kind == "process_exit":
            if role not in signaled:
                raise ValueError("Exit code without a signaled handle")
            once(exits, role, data["code"])
        elif kind == "process_active":
            if role not in registrations or role in signaled or "wrapper" not in signaled or role in active_after_exit:
                raise ValueError("Uncorroborated post-wrapper observation")
            active_after_exit.add(role)
        elif kind == "pipe_terminal":
            once(terminals, data["channel"], {key: data[key] for key in ("outcome", "source", "winerror")})
            terminal_order[data["channel"]] = event["seq"]
        elif kind == "stdin_writer_closed":
            if role not in registrations or role in stdin_writers_closed:
                raise ValueError("Writer close without unique process registration")
            stdin_writers_closed.add(role)
        elif kind == "fixture_marker":
            key = (role, data["marker"])
            if role not in stdin_writers_closed or key in markers:
                raise ValueError("Invalid fixture acknowledgement")
            markers.add(key)
        elif kind == "job_accounting":
            once(accounting, data["checkpoint"], {"active": data["active"], "total": data["total"]})
        elif kind == "force_requested":
            once(forces, data["target"], data["source"])
            force_order[data["target"]] = event["seq"]
        elif kind == "owner_acknowledged":
            if ack or "owner" not in registrations or forces.get("job") != "external_owner":
                raise ValueError("Unbound owner acknowledgement")
            ack = True
        elif kind == "receipt_checked":
            if receipt is not None:
                raise ValueError("Duplicate in-band receipt observation")
            receipt = data["present"]
        elif kind == "issue":
            issues.append([data["class"], data["code"]])
        elif kind == "observer_finalized":
            finish = data
        else:
            raise ValueError("Unexpected observer event")

    if finish and (finish["identity"] != start["identity"] or finish["outside_job"] != start["outside_job"]):
        raise ValueError("Observer finalization identity or boundary mismatch")
    complete = finish is not None and not unfinished_line
    live_targets = {role for role in registrations if role != "owner"}
    job_final = accounting.get("final", {})
    job_registered = accounting.get("registered", {})
    job_empty = job_final.get("active") == 0
    force_affected = live_targets if "job" in forces else {"wrapper"} if "wrapper" in forces else set()
    stdin = {role: "trusted_fixture_control_pipe" for role in ("wrapper", "server") if (role, "stdin_eof") in markers}
    output = {}
    for role in ("wrapper", "server"):
        channel = f"{role}_stdout"
        endpoint = terminals.get(channel)
        if endpoint:
            terminal = endpoint["outcome"]
            if terminal in ("peer_closed", "zero_read"):
                prior_force = any(target in force_order and force_order[target] < terminal_order[channel]
                                  for target in (("job", "wrapper") if role == "wrapper" else ("job",)))
                if prior_force:
                    terminal = "peer_closure_observed_after_force_request"
                elif (role, "stdout_finished") in markers:
                    terminal = "graceful_eof_observed"
                else:
                    terminal = "unattributed_peer_closure"
            output[role] = terminal
    # An empty job is independent of which individual exit codes were retrieved.
    required = {"wrapper", "server"}
    missing_observations = []
    for role in sorted(required | live_targets):
        for observed, label in ((registrations, "registration"), (signaled, "signaled_handle"), (exits, "exit_code")):
            if role not in observed:
                missing_observations.append(f"{role}.{label}")
        if role in required:
            if role not in stdin:
                missing_observations.append(f"{role}.stdin_eof")
            if role not in output:
                missing_observations.append(f"{role}.stdout_observation")
    if not job_empty:
        missing_observations.append("job.empty")
    if job_registered.get("active") != len(live_targets) or job_registered.get("total") != len(live_targets):
        missing_observations.append("job.registered_members")
    missing = (not required <= live_targets or set(registrations) != set(exits) or not job_empty
               or "job.registered_members" in missing_observations
               or job_final.get("total") != len(live_targets) or not start["outside_job"]
               or ("descendant" in live_targets and "descendant" not in active_after_exit))
    if not complete:
        status = "incomplete"
    elif any(kind == "invalid" for kind, _ in issues):
        status = "invalid"
    elif missing:
        status = "unavailable"
    elif (force_affected or any(code for key, code in exits.items() if key != "owner")
          or any(kind == "failure" for kind, _ in issues)
          or any(value in ("local_close", "read_error", "budget_exceeded") for value in output.values())):
        status = "observed_failure"
    elif (any(kind == "unavailable" for kind, _ in issues) or set(stdin) != required
          or any(output.get(role) != "graceful_eof_observed" for role in required)):
        status = "unavailable"
    else:
        status = "observed_success"
    return {
        "status": status, "scenario": start["scenario"], "observer_finalized": complete,
        "observer_outside_target_job": start["outside_job"], "registered_processes": registrations,
        "signaled_processes": sorted(signaled), "observed_exit_codes": exits,
        "active_after_wrapper_exit": sorted(active_after_exit), "job_accounting": accounting,
        "stdin_eof_sources": stdin, "stdout_classification": output, "pipe_terminals": terminals,
        "force_requests": forces, "external_owner_acknowledged": ack, "in_band_receipt_present": receipt,
        "issues": issues, "missing_observations": missing_observations,
    }


def validate(path):
    try:
        events, unfinished = read_events(path)
        return summarize(events, unfinished)
    except FileNotFoundError:
        return {"status": "unavailable", "reason": "record_missing", "observer_finalized": False}
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return {"status": "invalid", "reason": "record_or_chain_invalid", "observer_finalized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    result = validate(parser.parse_args().record)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(int(result["status"] not in ("observed_success", "observed_failure")))

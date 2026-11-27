"""Qualify a frozen v1 witness ledger against one named synthetic scenario."""

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent / "stage-1.4"))
from witness_record import SCENARIOS, read_events, summarize


SCHEMA = "wpai.benchmark.lifecycle-scenario-verdict.v1"
CONTRACT = "stage-1.4.1"
CREATED = "created_handle"
MEMBER = "bounded_job_membership"
OBSERVER = "observer_control"
EXTERNAL = "external_owner"
KILLED = 1
JOB_EXIT = 124
ZERO_EXITS = {"wrapper": 0, "server": 0}


@dataclass(frozen=True)
class Scenario:
    lifecycle: str
    exits: dict
    forces: tuple = ()
    issue: tuple = ()
    total: int = 2


CASES = {
    "normal": Scenario("observed_success", ZERO_EXITS),
    "server_zero": Scenario("observed_success", ZERO_EXITS),
    "server_nonzero": Scenario("observed_failure", {"wrapper": 0, "server": 7}),
    "external_tree": Scenario("observed_failure", {"wrapper": JOB_EXIT, "server": JOB_EXIT, "owner": KILLED},
                              (("job", EXTERNAL), ("owner", OBSERVER))),
    "wrapper_only": Scenario("observed_failure", {"wrapper": KILLED, "server": JOB_EXIT},
                             (("wrapper", OBSERVER), ("job", OBSERVER))),
    "descendant": Scenario("observed_failure", {"wrapper": 0, "server": JOB_EXIT, "descendant": JOB_EXIT},
                           (("job", OBSERVER),), total=3),
    "local_pipe_close": Scenario("observed_failure", dict.fromkeys(ZERO_EXITS, JOB_EXIT), (("job", OBSERVER),)),
    "channel_broken": Scenario("unavailable", ZERO_EXITS, issue=("unavailable", "channel_disconnected")),
    "missing_registration": Scenario("unavailable", {"wrapper": 0}, issue=("unavailable", "missing_registration")),
    "missing_exit": Scenario("unavailable", {"wrapper": 0, "server": None}, issue=("unavailable", "missing_exit")),
    "identity_mismatch": Scenario("invalid", ZERO_EXITS, issue=("invalid", "identity_mismatch")),
    "timeout": Scenario("observed_failure", dict.fromkeys(ZERO_EXITS, JOB_EXIT), (("job", OBSERVER),),
                        issue=("failure", "timeout")),
}


class Gate:
    def __init__(self, events):
        self.events = events
        self.missing = set()
        self.conflicts = set()

    def find(self, kind, **selector):
        return [event for event in self.events if event["kind"] == kind
                and all(event["data"].get(key) == value for key, value in selector.items())]

    def require(self, label, observed, **facts):
        if not observed:
            self.missing.add(label)
            return None
        event = observed[0]
        if len(observed) != 1 or any(event["data"].get(key) != value for key, value in facts.items()):
            self.conflicts.add(label)
        return event

    def forbid(self, label, observed):
        if observed:
            self.conflicts.add(label)

    def order(self, label, *events):
        if all(event is not None for event in events):
            positions = [event["seq"] for event in events]
            if positions != sorted(set(positions)):
                self.conflicts.add(label)

    def peer_closed(self, channel):
        found = self.find("pipe_terminal", channel=channel)
        event = self.require(f"{channel}.terminal", found, source="ReadFile")
        if event and event["data"]["outcome"] not in ("peer_closed", "zero_read"):
            self.conflicts.add(f"{channel}.peer_eof")
        return event


def common(gate, name, case):
    gate.require("observer.outside_target_job", gate.find("observer_started"), outside_job=True)
    gate.require("observer.finalized_outside_job", gate.find("observer_finalized"), outside_job=True)
    registered = gate.require("job.registered", gate.find("job_accounting", checkpoint="registered"),
                              active=case.total, total=case.total)
    final = gate.require("job.final", gate.find("job_accounting", checkpoint="final"), active=0, total=case.total)
    gate.order("job.checkpoint_order", registered, final)
    known_roles = set(case.exits)
    registrations, signals, exits = {}, {}, {}
    for role, code in case.exits.items():
        source = MEMBER if role == "descendant" or (role == "server" and name == "external_tree") else CREATED
        registration = gate.require(f"{role}.registered", gate.find("process_registered", role=role),
                                    in_job=role != "owner", source=source)
        registrations[role] = registration
        if role != "owner":
            gate.order(f"{role}.registered_before_job_checkpoint", registration, registered)
        signals[role] = gate.require(f"{role}.signaled", gate.find("handle_signaled", role=role))
        gate.order(f"{role}.signaled_after_job_registration", registered, signals[role], final)
        results = gate.find("process_exit", role=role)
        if code is None:
            gate.forbid(f"{role}.unexpected_exit_code", results)
        else:
            exits[role] = gate.require(f"{role}.exit_code", results, code=code)
            gate.order(f"{role}.exit_observation_order", signals[role], exits[role], final)
    for kind in ("process_registered", "handle_signaled", "process_exit"):
        gate.forbid(f"{kind}.unexpected_role", [event for event in gate.find(kind)
                                                if event["data"]["role"] not in known_roles])
    requests = {}
    for target, source in case.forces:
        requests[target] = gate.require(f"force.{target}", gate.find("force_requested", target=target), source=source)
        gate.order(f"force.{target}.order", registered, requests[target], final)
    gate.forbid("unexpected_force", [event for event in gate.find("force_requested")
                                    if event["data"]["target"] not in requests])
    if name != "external_tree":
        gate.forbid("unexpected_owner_acknowledgment", gate.find("owner_acknowledged"))
        gate.forbid("unexpected_in_band_receipt_check", gate.find("receipt_checked"))
    issue = None
    if case.issue:
        category, code = case.issue
        issue = gate.require(f"issue.{code}", gate.find("issue"), **{"class": category, "code": code})
        gate.order("issue.order", registered, issue, final)
    else:
        gate.forbid("unexpected_issue", gate.find("issue"))
    return registered, final, registrations, signals, exits, requests, issue


def natural_pipe(gate, role, ready, signal, final, *, broken_control=False):
    writer = gate.require(f"{role}.stdin_writer_closed", gate.find("stdin_writer_closed", role=role))
    stdout = gate.peer_closed(f"{role}_stdout")
    control = gate.peer_closed(f"{role}_control")
    gate.order(f"{role}.stdin_close_order", ready, writer, signal, final)
    gate.order(f"{role}.stdout_order", writer, stdout, final)
    gate.order(f"{role}.control_pipe_order", writer, control, final)
    if broken_control:
        gate.forbid(f"{role}.unavailable_markers", gate.find("fixture_marker", role=role))
    else:
        for marker in ("stdin_eof", "stdout_finished"):
            evidence = gate.require(f"{role}.{marker}", gate.find("fixture_marker", role=role, marker=marker))
            gate.order(f"{role}.{marker}.recording_order", control, evidence, final)
            gate.order(f"{role}.{marker}.after_signal", signal, evidence)
    return writer, control


def check_scenario(gate, name, case):
    ready, final, registrations, signals, exits, forces, issue = common(gate, name, case)
    survivor = {"wrapper_only": "server", "descendant": "descendant"}.get(name)
    gate.forbid("unexpected_survivor", [event for event in gate.find("process_active")
                                      if event["data"]["role"] != survivor])
    if not survivor:
        gate.forbid("unexpected_after_wrapper_accounting", gate.find("job_accounting", checkpoint="after_wrapper_exit"))
    if forces:
        gate.forbid("unexpected_graceful_markers", gate.find("fixture_marker"))
        gate.forbid("unexpected_stdin_close", gate.find("stdin_writer_closed"))
    if name == "external_tree":
        ack = gate.require("owner_acknowledged", gate.find("owner_acknowledged"))
        receipt = gate.require("receipt_checked", gate.find("receipt_checked"), present=False)
        endpoint = gate.peer_closed("wrapper_stdout")
        gate.order("external_owner.request_ack_order", registrations.get("owner"), forces["job"], ack)
        gate.order("wrapper.stdout_closure_after_force", forces["job"], endpoint, receipt, final)
        for role in ZERO_EXITS:
            gate.order(f"external_owner.{role}.exit_order", ack, signals[role], exits[role], forces["owner"])
        gate.order("external_owner.finalization_order", forces["owner"], signals["owner"], exits["owner"], receipt, final)
    elif survivor:
        active = gate.require(f"{survivor}.active_after_wrapper_exit", gate.find("process_active", role=survivor))
        after = gate.require("job.after_wrapper_exit", gate.find("job_accounting", checkpoint="after_wrapper_exit"),
                             active=case.total - 1, total=case.total)
        gate.order("survivor.before_cleanup", exits["wrapper"], active, after, forces["job"], signals[survivor])
        if name == "wrapper_only":
            gate.order("wrapper.force_before_signal", forces["wrapper"], signals["wrapper"])
        else:
            gate.order("server.cleanup_before_signal", forces["job"], signals["server"])
    elif name in ("local_pipe_close", "timeout"):
        for role in ZERO_EXITS:
            gate.order(f"{role}.cleanup_before_signal", forces["job"], signals[role])
        if name == "timeout":
            gate.order("timeout.before_cleanup", issue, forces["job"])
        else:
            closure = gate.require("server_stdout.local_close", gate.find("pipe_terminal", channel="server_stdout"),
                                   outcome="local_close", source="observer_closed_reader")
            gate.order("server_stdout.close_before_cleanup", ready, closure, forces["job"])
    else:
        wrapper_writer, _ = natural_pipe(gate, "wrapper", ready, signals["wrapper"], final)
        if name == "missing_registration":
            for channel in ("server_stdout", "server_control"):
                endpoint = gate.peer_closed(channel)
                gate.order(f"{channel}.observed_before_missing_registration", endpoint, issue)
            gate.forbid("missing_server.unattested_markers", gate.find("fixture_marker", role="server"))
            gate.forbid("missing_server.unattributed_stdin_close", gate.find("stdin_writer_closed", role="server"))
            return
        server_writer, control = natural_pipe(gate, "server", ready, signals["server"], final,
                                              broken_control=name == "channel_broken")
        if name in ("server_zero", "server_nonzero"):
            gate.order("server.natural_exit_before_wrapper_eof", exits["server"], wrapper_writer)
        else:
            gate.order("wrapper.natural_exit_before_server_eof", exits["wrapper"], server_writer)
        if name == "channel_broken":
            gate.order("channel_break.after_peer_close", control, issue)
            gate.order("channel_break.after_exit", exits["server"], issue)
        elif name == "missing_exit":
            gate.order("missing_exit.after_signal", signals["server"], issue)
        elif name == "identity_mismatch":
            gate.order("identity_mismatch.before_shutdown", issue, wrapper_writer)


def result(scenario, lifecycle, qualification, *, missing=(), conflicts=(), unobserved=()):
    return {"schema": SCHEMA, "contract": CONTRACT, "scenario": scenario, "lifecycle_status": lifecycle,
            "qualification": qualification, "missing": sorted(missing), "conflicts": sorted(conflicts),
            "unobserved": sorted(unobserved)}


def qualify(path, scenario):
    """Read the serialized ledger once and qualify its declared scenario."""
    if scenario not in SCENARIOS:
        raise ValueError("Unknown synthetic scenario")
    try:
        events, unfinished = read_events(path)
        # Reuse v1 schema, integrity, unique identities and cross-event invariants.
        summary = summarize(events, unfinished)
        lifecycle = summary["status"]
    except FileNotFoundError:
        return result(scenario, "unavailable", "unavailable", missing=("record",))
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return result(scenario, "invalid", "invalid", conflicts=("v1_record",))
    if events and events[0]["data"]["scenario"] != scenario:
        return result(scenario, lifecycle, "fail", conflicts=("scenario",))
    if lifecycle == "incomplete":
        return result(scenario, lifecycle, "incomplete", missing=("observer_finalized",))
    if scenario == "observer_crash":
        return result(scenario, lifecycle, "fail", conflicts=("unexpected_observer_finalization",))

    case = CASES[scenario]
    gate = Gate(events)
    check_scenario(gate, scenario, case)
    if not gate.missing and lifecycle != case.lifecycle:
        gate.conflicts.add("lifecycle_status")
    verdict = "fail" if gate.conflicts else "unavailable" if gate.missing else "pass"
    return result(scenario, lifecycle, verdict, missing=gate.missing, conflicts=gate.conflicts,
                  unobserved=summary.get("missing_observations", ()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    verdict = qualify(args.record, args.scenario)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return int(verdict["qualification"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())

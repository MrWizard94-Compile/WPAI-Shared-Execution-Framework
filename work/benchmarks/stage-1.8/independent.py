"""Independently own the Stage 1.8 ledger, kernel observations and recovery."""

from contextlib import ExitStack
from hashlib import sha256
import hmac
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boundary import (ACTORS, CASES, CONTROLLER_MASKS, INJECTED_EXIT, JOBS, MEMBERSHIP, OBSERVE_PROCESS,
                      RECOVERED_EXIT, RECOVERY_MS, RUN_SECONDS, WITNESS_MASKS,
                      checked_jobs, deny_network, receive, received, rights, send, snapshot, wait_until, win)
from contract import REQUEST, RESPONSE_MARK, canonical, observation, require
from journal import PIPE_ROLES, SCHEMA, Ledger, TERMINAL_STATUS, actor_trace, expected_roles, totals, validate
from witness import REQUEST_HOPS, RESPONSE_HOPS


TRACE_FIELDS = {
    "wire": {"boundary", "bytes", "sha256"},
    "server_read_waiting": {"actor"},
    "oracle": {"actor", "tool", "facts", "calls"},
    "writer_close": {"channel", "writer", "method"},
    "terminal_read": {"channel", "reader", "method", "status", "bytes"},
    "server_empty_read": {"actor", "bytes"},
    "signaled": {"role", "process", "method"},
    "exit": {"role", "process", "method", "code"},
    "job": {"job", "phase", "members", "active", "total", "method"},
}


class ControllerClosed(Exception):
    pass


class Independent:
    def __init__(self, case, journal, controller_handle, incoming, ack, status, jobs, stack):
        self.case, self.ledger, self.jobs, self.stack = case, journal, jobs, stack
        self.controller_handle = controller_handle
        self.incoming, self.ack, self.status = win.Reader(incoming), ack, status
        self.deadline = time.monotonic() + RUN_SECONDS
        self.secret = os.urandom(32)
        self.processes = {}
        self.tokens = {}
        self.trace = []
        self.recovery_started = None

    def record(self, event, actor="witness", **fields):
        self.ledger.add(event, actor=actor, **fields)

    def next_packet(self):
        row = receive(self.incoming, self.deadline)
        if row is None:
            raise ControllerClosed("Controller telemetry closed")
        return row

    def expect(self, kind, *fields, **exact):
        row = self.next_packet()
        require(row.get("kind") == kind and row.keys() == {"kind", *fields, *exact}
                and all(type(row[key]) is type(value) and row[key] == value for key, value in exact.items()),
                f"Unexpected control frame at {kind}")
        return row

    def acknowledge(self):
        send(self.ack, status="durable")

    def opaque(self, *values):
        return hmac.new(self.secret, canonical([self.ledger.run, *values]), sha256).hexdigest()

    def assert_active(self, role):
        process = self.processes[role]
        require(not process.signaled() and win.identity(process.handle) == process.identity,
                f"{role} lost its retained identity")
        names = tuple(scope for scope in JOBS if win.in_job(process.handle, self.jobs[scope]))
        require(names == MEMBERSHIP[role], f"{role} lacks independent job containment")

    def register(self, role, identity):
        require(role not in self.processes and all(p.identity.pid != identity.pid for p in self.processes.values()),
                "Duplicate controlled process registration")
        process = win.Process(identity.pid, expected=identity)
        self.stack.callback(process.close)
        require(rights(process.handle) == OBSERVE_PROCESS, "Process handle exceeded query and wait access")
        self.processes[role] = process
        self.assert_active(role)
        self.tokens[role] = self.opaque("process", identity.pid)
        self.record("registered", role=role, jobs=list(MEMBERSHIP[role]), process=self.tokens[role],
                    creation=self.opaque("creation", identity.pid, identity.created), source="retained_handle")

    def register_report(self, role):
        row = self.expect("registration", "pid", "created", role=role)
        require(type(row["pid"]) is int and 0 < row["pid"] <= 0xffffffff
                and type(row["created"]) is int and row["created"] > 0, "Invalid private process identity")
        self.register(role, win.Identity(row["pid"], row["created"]))
        self.acknowledge()

    def active(self, phase, role):
        self.assert_active(role)
        self.record("active", phase=phase, role=role, process=self.tokens[role],
                    source="WaitForSingleObject+IsProcessInJob")

    def sample(self, scope, known, total):
        pids, active, count = snapshot(self.jobs[scope])
        require(pids == {self.processes[role].identity.pid for role in known} and count == total,
                f"{scope} independent membership or accounting differs")
        return {"members": sorted(known), "active": active, "total": count}

    def job(self, scope, phase, known, total):
        self.record("job", scope=scope, phase=phase, **self.sample(scope, known, total),
                    source="QueryInformationJobObject")

    def phase_job(self, scope, roles, total):
        row = self.expect("trace", "row")["row"]
        result = self.sample(scope, roles, total)
        require(canonical(row) == canonical({"event": "job", "job": scope, "phase": "startup", **result,
                                            "method": "QueryInformationJobObject"}), "Bad startup job report")
        self.record("job", scope=scope, phase="startup", **result, source="QueryInformationJobObject")
        self.acknowledge()

    def trace_event(self, row):
        require(isinstance(row, dict) and row.get("event") in TRACE_FIELDS, "Unknown controller actor observation")
        event = row["event"]
        require(row.keys() == TRACE_FIELDS[event] | {"event"}, "Unexpected actor observation fields")
        if event == "wire":
            name = row["boundary"]
            require(name in (*REQUEST_HOPS, *RESPONSE_HOPS), "Unknown Stage 1.6 wire boundary")
            expected = observation(REQUEST) if name in REQUEST_HOPS else RESPONSE_MARK
            require(canonical({key: row[key] for key in ("bytes", "sha256")}) == canonical(expected),
                    "Unexpected fixed fixture bytes")
        if event in ("exit", "signaled"):
            role = row["role"]
            require(role in ACTORS and self.processes[role].signaled(), "Controller reported an unsignaled actor")
            if event == "exit":
                require(type(row["code"]) is int and row["code"] == self.processes[role].exit_code(),
                        "Controller disagrees with retained process exit code")
            row["process"] = self.tokens[role]
        if event == "job":
            require(row["job"] in ("subject", "fixture") and row["phase"] == "final", "Unexpected actor job report")
            actual = self.sample(row["job"], [], totals(self.case)[row["job"]])
            require(all(type(row[key]) is type(value) and row[key] == value for key, value in actual.items()),
                    "Controller disagrees with independent final job accounting")
        self.record("actor_trace", actor="controller", observation=row)
        self.trace.append((row, time.monotonic_ns() - self.ledger.origin))
        self.acknowledge()

    def boot(self):
        self.record("start", schema=SCHEMA, case=self.case)
        self.register("witness", win.identity(win.current_process()))
        controller_mask = rights(self.controller_handle)
        require(controller_mask == OBSERVE_PROCESS and win.integrity(self.controller_handle) == 4096,
                "Controller bootstrap rights or integrity differ")
        self.register("controller", win.identity(self.controller_handle))
        self.record("witness_rights", jobs={key: rights(job.handle) for key, job in self.jobs.items()},
                    retained_controller=controller_mask, source="NtQueryObject")
        for scope in JOBS:
            self.job(scope, "before_release", ["controller"] if scope == "guard" else [], int(scope == "guard"))
        self.record("witness_ready")
        send(self.status, kind="ready")
        self.expect("protected_storage", canary_write_denied=True, journal_write_denied=True)
        self.record("protected_storage", actor="controller", canary_write_denied=True, journal_write_denied=True,
                    jobs=CONTROLLER_MASKS)
        self.acknowledge()
        if self.case == "before_launch":
            return
        self.register_report("owner")
        self.register_report("server")
        self.phase_job("fixture", ["server"], 1)
        release = self.case != "in_flight"
        self.expect("fixture_gate", released=release)
        self.record("fixture_gate", released=release)
        self.acknowledge()
        if release:
            self.expect("fixture_ready")
            self.record("fixture_ready", actor="controller")
            self.acknowledge()
        self.register_report("root")
        self.register_report("relay")
        self.phase_job("subject", ["relay", "root"], 2)
        self.expect("subject_gate")
        self.record("subject_gate")
        self.acknowledge()
        self.expect("actors_ready")
        self.record("actors_ready", actor="controller")
        self.acknowledge()

    def exit(self, role):
        process = self.processes[role]
        require(process.signaled(), f"{role} has no retained signal")
        code = process.exit_code()
        self.record("signaled", role=role, process=self.tokens[role], source="WaitForSingleObject")
        self.record("exit", role=role, process=self.tokens[role], code=code, source="GetExitCodeProcess")
        return code

    def detect_terminal(self):
        require(receive(self.incoming, self.deadline) is None, "Unexpected data after shutdown gate")
        require(TERMINAL_STATUS(self.incoming.terminal), "No terminal controller ReadFile observation")
        self.record("controller_pipe_terminal", status=self.incoming.terminal, source="ReadFile", bytes=0)
        wait_until(self.processes["controller"].signaled, self.deadline)
        return self.exit("controller")

    def wait_jobs(self, deadline):
        wait_until(lambda: all(job.accounting().active == 0 for job in self.jobs.values())
                   and all(process.signaled() for role, process in self.processes.items() if role != "witness"),
                   deadline)

    def recover(self):
        self.recovery_started = time.monotonic_ns()
        self.record("recovery_started", target="guard", budget_ms=RECOVERY_MS,
                    start_ns=self.recovery_started - self.ledger.origin)
        win.checked(win.terminate_job(self.jobs["guard"].handle, RECOVERED_EXIT))
        self.record("recovery_force", target="guard", requested_exit=RECOVERED_EXIT, source="TerminateJobObject")
        self.wait_jobs(self.recovery_started / 1_000_000_000 + RECOVERY_MS / 1000)
        for role in expected_roles(self.case)[1:]:
            self.exit(role)
        for scope in JOBS:
            self.job(scope, "final", [], totals(self.case)[scope])
        elapsed = time.monotonic_ns() - self.recovery_started
        require(elapsed <= RECOVERY_MS * 1_000_000, "Recovery duration exceeded")
        self.record("recovery_settled", elapsed_ns=elapsed)
        for channel in PIPE_ROLES:
            reason = "actors_not_started" if self.case == "before_launch" else "controller_lost"
            self.record("observation_unavailable", channel=channel, reason=reason)

    def checkpoint(self):
        trace = actor_trace(self.trace, self.tokens)
        if self.case == "in_flight":
            for boundary in REQUEST_HOPS[:3]:
                trace.expect("wire", boundary=boundary, **observation(REQUEST))
        elif self.case == "response_verified":
            trace.frames()
        require(trace.index == len(trace.events), "Unexpected observations before the fault checkpoint")
        roles = expected_roles(self.case)
        for role in roles:
            self.active("checkpoint", role)
        for scope in JOBS:
            self.job(scope, "checkpoint", [role for role in roles if scope in MEMBERSHIP[role]], totals(self.case)[scope])
        self.record("checkpoint", case=self.case, fixture_gate_held=self.case == "in_flight")
        send(self.status, kind="inject", case=self.case)
        require(self.detect_terminal() == INJECTED_EXIT, "Controller termination was not the injected exit")
        self.record("controller_lost", basis="terminal_ReadFile_and_retained_exit")
        self.active("after_controller_loss", "witness")
        self.recover()
        return "incomplete"

    def normal_finish(self):
        trace = actor_trace(self.trace, self.tokens)
        trace.frames()
        trace.graceful_fixture("normal")
        require(trace.index == len(trace.events), "Unexpected normal teardown observation")
        self.record("controller_finished", actor="controller")
        self.acknowledge()
        require(self.detect_terminal() == 0, "Normal controller exit was nonzero")
        self.wait_jobs(self.deadline)
        for scope in JOBS:
            self.job(scope, "final", [], totals(self.case)[scope])
        return "observed_success"

    def observe(self):
        self.boot()
        while True:
            row = self.next_packet()
            if row.keys() == {"kind", "row"} and row["kind"] == "trace":
                self.trace_event(row["row"])
            elif self.case == "normal" and row == {"kind": "finish"}:
                return self.normal_finish()
            elif self.case != "normal" and row == {"kind": "checkpoint", "case": self.case}:
                return self.checkpoint()
            else:
                raise ValueError("Unexpected controller message")

    def emergency(self, cause):
        started = self.recovery_started if self.recovery_started is not None else time.monotonic_ns()
        job_result = None
        try:
            if self.recovery_started is None:
                win.checked(win.terminate_job(self.jobs["guard"].handle, RECOVERED_EXIT))
            self.wait_jobs(started / 1_000_000_000 + RECOVERY_MS / 1000)
            job_result = {}
            for scope, job in self.jobs.items():
                pids, active, total = snapshot(job)
                require(not pids and active == 0, "Job survived emergency cleanup")
                job_result[scope] = {"members": [], "active": active, "total": total}
        except (OSError, ValueError):
            job_result = None
        exits = {role: process.exit_code() for role, process in self.processes.items()
                 if role != "witness" and process.signaled()}
        elapsed = time.monotonic_ns() - started
        if elapsed > RECOVERY_MS * 1_000_000:
            job_result = None
        self.assert_active("witness")
        self.record("emergency", reason=cause, settled=job_result is not None, elapsed_ns=elapsed,
                    controller_terminal=self.incoming.terminal, exits=exits, jobs=job_result)
        self.record("terminal", outcome="unavailable", reason="unscripted_loss_or_unsettled", case=self.case,
                    process=self.tokens["witness"])


def main():
    case, scratch, *values = sys.argv[1:]
    require(case in CASES, "Unknown witness case")
    deny_network()
    path = Path(scratch) / "journal" / "witness.jsonl"
    with ExitStack() as stack:
        controller, incoming, ack, status, *job_handles = received(stack, values, 7)
        jobs = checked_jobs(job_handles, WITNESS_MASKS)
        with win.open_evidence(path) as writer:
            witness = Independent(case, Ledger(writer), controller, incoming, ack, status, jobs, stack)
            try:
                outcome = witness.observe()
            except (ValueError, EOFError, OSError, ControllerClosed, KeyError, TypeError) as error:
                cause = ("controller_pipe_closed" if isinstance(error, ControllerClosed) else
                         "bounded_deadline" if isinstance(error, TimeoutError) else "invalid_or_unsettled")
                witness.emergency(cause)
                outcome = "unavailable"
            else:
                witness.active("final", "witness")
                witness.record("terminal", outcome=outcome, case=case, process=witness.tokens["witness"])
            verified = validate(path.read_bytes())
            require(verified["valid"] and verified["outcome"] == outcome, "Witness rejected its terminal journal")
            send(status, kind="validated", outcome=outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

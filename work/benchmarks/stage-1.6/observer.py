"""Independent live Windows observer for the four bounded synthetic scenarios."""

from contextlib import ExitStack
from hashlib import sha256
import hmac
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import win
from contract import SCENARIOS, canonical, parse, prepare, require
from witness import (DUPLICATE_WINDOW_MS, Ledger, MEMBERSHIP, READERS, REQUEST_HOPS, RESPONSE_HOPS,
                     SCHEMA, validate)


class Observer:
    def __init__(self, ledger, directory, fixture, stack, jobs):
        self.ledger, self.directory, self.fixture, self.stack, self.jobs = ledger, directory, fixture, stack, jobs
        self.processes = {}
        self.tokens = {}
        self.children = {}
        self.commands = {}
        self.readers = {}
        self.secret = os.urandom(32)
        self.deadline = time.monotonic() + 35

    def until(self, predicate):
        deadline = self.cutoff()
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError("Bounded process observation expired")
            time.sleep(0.002)

    def cutoff(self):
        return min(self.deadline, time.monotonic() + win.TIMEOUT)

    def own(self, handle):
        self.stack.callback(handle.close)
        return handle

    def pipe(self):
        return tuple(self.own(handle) for handle in win.pipe())

    def mailbox(self, role):
        read, write = self.pipe()
        self.readers[role] = win.Reader(read.value)
        return write

    def control(self, role):
        read, write = self.pipe()
        self.commands[role] = write
        return read

    def send(self, role, value):
        win.write(self.commands[role].value, value.encode("ascii") + b"\n")

    def packet(self, actor, event, *fields, **exact):
        data = self.readers[actor].line(self.cutoff())
        require(bool(data), f"{actor} control channel closed before {event}")
        row = parse(data)
        require(canonical(row) + b"\n" == data and row.pop("event") == event
                and row.keys() == {*fields, *exact} and all(row[k] == v for k, v in exact.items()),
                f"{actor} control record mismatched {event}")
        return row

    def direct(self, role, handles, **options):
        actual_role = "subject" if role == "root" else role
        child = win.spawn(actual_role, handles, **options)
        self.stack.callback(child.close)
        self.children[role] = child
        self.attach(role, win.identity(child.process.value))
        for handle in handles:
            handle.close()
        return child

    def attach_reported(self, role, source):
        row = self.packet(source, "created", "pid", "created", role=role)
        self.attach(role, win.Identity(row["pid"], row["created"]))

    def attach(self, role, baseline):
        process = win.Process(baseline.pid, expected=baseline)
        self.stack.callback(process.close)
        self.processes[role] = process
        self.assert_active(role)
        pid, created = baseline.pid, baseline.created
        process_token = self.opaque(["process", pid])
        self.tokens[role] = process_token
        self.ledger.add("registered", role=role, job=MEMBERSHIP[role], process=process_token,
                        creation=self.opaque(["creation", pid, created]), method="retained_creation_handle")

    def opaque(self, values):
        return hmac.new(self.secret, canonical([self.ledger.run, *values]), sha256).hexdigest()

    def assert_active(self, role):
        process = self.processes[role]
        require(not process.signaled() and win.identity(process.handle) == process.identity,
                f"Retained {role} identity inactive")
        for name in ("subject", "fixture"):
            require(win.in_job(process.handle, self.jobs[name]) == (MEMBERSHIP[role] == name),
                    f"{role} has unexpected {name} containment")

    def active(self, role, phase):
        self.assert_active(role)
        self.ledger.add("active", role=role, process=self.tokens[role], phase=phase, job=MEMBERSHIP[role],
                        method="WaitForSingleObject+IsProcessInJob")

    def exit(self, role):
        process = self.processes[role]
        self.until(process.signaled)
        self.ledger.add("signaled", role=role, process=self.tokens[role], method="WaitForSingleObject")
        self.ledger.add("exit", role=role, process=self.tokens[role], code=process.exit_code(),
                        method="GetExitCodeProcess")

    def job(self, name, phase, roles):
        job = self.jobs[name]
        expected = {self.processes[role].identity.pid for role in roles}
        self.until(lambda: win.members(job) == expected and job.accounting().active == len(expected))
        result = job.accounting()
        require(win.members(job) == expected and result.active == len(expected),
                f"{name} membership changed during accounting")
        self.ledger.add("job", job=name, phase=phase, members=sorted(roles), active=result.active,
                        total=result.total, method="QueryInformationJobObject")

    def read(self, channel):
        role = READERS[channel]
        result = self.packet(role, "read_terminal", "status", channel=channel)
        self.terminal(channel, result["status"])

    def terminal(self, channel, status):
        require(type(status) is int and status in (0, 38, 109), "No known terminal ReadFile status")
        self.ledger.add("terminal_read", channel=channel, reader=READERS[channel], method="ReadFile",
                        status=status, bytes=0)

    def close(self, actor, channel, writer):
        self.packet(actor, "writer_closed", channel=channel, writer=writer)
        self.ledger.add("writer_close", channel=channel, writer=writer,
                        method="CRT_close" if actor == "server" else "CloseHandle")

    def unavailable(self, *channels):
        for channel in channels:
            self.ledger.add("read_unavailable", channel=channel, reader=READERS[channel], reason="reader_terminated")

    def setup(self, scenario):
        self.ledger.add("start", schema=SCHEMA, scenario=scenario)
        self.attach("observer", win.identity(win.current_process()))
        split_request, relay_writer = self.pipe()
        relay_reader, split_response = self.pipe()
        server_input, server_writer = self.pipe()
        # Only these scenarios create a deliberate duplicate of the final fixture writer.
        extra = self.own(win.copy_handle(server_writer.value)) if scenario in ("duplicate_writer", "owner_loss") else None
        assign_only = self.own(win.copy_handle(self.jobs["fixture"].handle, 0x0001))  # JOB_OBJECT_ASSIGN_PROCESS
        owner_handles = [self.control("owner"), self.mailbox("owner"), split_request, split_response,
                         server_input, server_writer, self.mailbox("server"), assign_only]
        if scenario == "duplicate_writer":
            owner_handles.append(extra)
        self.direct("owner", owner_handles, args=(str(self.fixture),)).start()
        self.attach_reported("server", "owner")
        self.job("fixture", "startup", ["server"])
        self.ledger.add("startup_gate", role="server")
        self.send("owner", "start_server")
        self.packet("server", "ready")
        root_handles = [self.control("root"), self.mailbox("root"), relay_writer, relay_reader, self.mailbox("relay")]
        self.direct("root", root_handles, job_handle=self.jobs["subject"].handle).start()
        self.send("root", "spawn_relay")
        self.attach_reported("relay", "root")
        self.job("subject", "startup", ["root", "relay"])
        self.ledger.add("startup_gate", role="relay")
        self.send("root", "start_relay")
        self.packet("relay", "ready")
        if extra is not None:
            self.ledger.add("writer_retained", channel="fixture_request",
                            writer="owner_duplicate" if scenario == "duplicate_writer" else "observer_guard")
        return extra

    def transaction(self):
        self.send("root", "request")
        for boundary in (*REQUEST_HOPS, *RESPONSE_HOPS):
            if boundary == RESPONSE_HOPS[0]:
                self.packet("server", "server_read_waiting")
                self.ledger.add("server_read_waiting", actor="server")
            actor = boundary.split("_", 1)[0]
            row = self.packet(actor, "wire", "bytes", "sha256", boundary=boundary)
            self.ledger.add("wire", **row)
        self.packet("root", "oracle_exact")
        self.ledger.add("oracle", actor="root", tool="repo_health_v1", facts=12, calls=1)

    def force(self):
        right = self.own(win.copy_handle(self.jobs["subject"].handle, 0x0008))  # JOB_OBJECT_TERMINATE
        canary = self.directory / "control-isolation-canary"
        canary.write_bytes(b"Stage 1.6 synthetic storage canary\n")
        controller = self.direct("force", [self.control("force"), self.mailbox("force"), right],
                                 args=(str(canary),), job_handle=self.jobs["force_guard"].handle, low=True)
        require(win.integrity(controller.process.value) == 4096, "External force controller integrity mismatch")
        controller.start()
        self.packet("force", "isolation_denied", read=True, write=True)
        self.ledger.add("force_isolated", actor="force", integrity="low", storage_read_denied=True,
                        storage_write_denied=True, job_right="JOB_OBJECT_TERMINATE")
        for role in ("root", "relay"):
            self.active(role, "before_force")
        self.ledger.add("force_request", target="subject", actor="observer")
        self.send("force", "force")
        self.packet("force", "force_ack")
        self.ledger.add("force_ack", target="subject", actor="force", method="TerminateJobObject")
        for role in ("force", "root", "relay"):
            self.exit(role)
        self.job("subject", "final", [])
        for role in ("owner", "server", "observer"):
            self.active(role, "after_subject_force")
        self.job("fixture", "after_subject_force", ["server"])
        self.ledger.add("writer_close", channel="split_request", writer="relay", method="process_terminated")
        self.unavailable("front_request", "front_response")

    def owner_loss(self, guard):
        self.active("owner", "before_loss")
        self.ledger.add("owner_stop", actor="observer", method="TerminateProcess")
        self.children["owner"].kill(win.OWNER_LOST)
        self.exit("owner")
        pipe = self.readers["owner"]
        require(pipe.line(self.cutoff()) == b"", "Unexpected owner control data after loss")
        self.terminal("owner_control", pipe.terminal)
        self.ledger.add("owner_lost", source="retained_handle_and_control_ReadFile")
        for role in ("observer", "server"):
            self.active(role, "after_owner_loss")
        self.job("fixture", "after_owner_loss", ["server"])
        for name, roles in (("fixture", ("server",)), ("subject", ("root", "relay"))):
            self.ledger.add("recovery_force", target=name, actor="observer", method="TerminateJobObject")
            self.jobs[name].terminate()
            for role in roles:
                self.exit(role)
            self.job(name, "final", [])
        guard.close()
        self.ledger.add("writer_close", channel="fixture_request", writer="observer_guard", method="CloseHandle")
        self.unavailable(*(channel for channel in READERS if channel != "owner_control"))

    def graceful_fixture(self, scenario):
        forced = scenario == "external_termination"
        if forced:
            self.force()
        else:
            self.send("root", "close_root")
            self.close("root", "front_request", "root")
            self.read("front_request")
            self.close("relay", "split_request", "relay")
        self.send("owner", "check_split_input")
        self.read("split_request")
        self.close("owner", "split_response", "owner")
        if forced:
            self.unavailable("split_response")
        else:
            self.read("split_response")
            self.close("relay", "front_response", "relay")
            self.read("front_response")
            self.exit("relay")
            self.exit("root")
            self.job("subject", "final", [])
        self.send("owner", "close_primary")
        self.close("owner", "fixture_request", "owner_primary")
        if scenario == "duplicate_writer":
            self.active("server", "duplicate_open")
            pipe = self.readers["server"]
            end = time.monotonic() + DUPLICATE_WINDOW_MS / 1000
            while time.monotonic() < end:
                pipe.poll()
                require(not pipe.buffer and pipe.terminal is None, "Fixture reported EOF before its last writer closed")
                self.assert_active("server")
                time.sleep(0.002)
            self.ledger.add("still_open", channel="fixture_request", result="no_terminal_report",
                            window_ms=DUPLICATE_WINDOW_MS)
            self.send("owner", "close_duplicate")
            self.close("owner", "fixture_request", "owner_duplicate")
        self.read("fixture_request")
        self.packet("server", "server_empty_read")
        self.ledger.add("server_empty_read", actor="server", bytes=0)
        self.close("server", "fixture_response", "server")
        self.send("owner", "drain")
        self.read("fixture_response")
        self.exit("server")
        self.exit("owner")
        self.job("fixture", "final", [])

    def run(self, scenario, timeout_probe):
        guard = self.setup(scenario)
        if timeout_probe:
            self.deadline = time.monotonic() + 0.1
            self.readers["server"].line(self.cutoff())  # No request is released in this timeout test.
            raise ValueError("Unexpected server telemetry during the timeout test")
        self.transaction()
        if scenario == "owner_loss":
            self.owner_loss(guard)
        else:
            self.graceful_fixture(scenario)
        self.assert_active("observer")
        self.ledger.add("finalized", actor="observer", process=self.tokens["observer"], job="outside")

    def recover_timeout(self):
        for job in self.jobs.values():
            if job.accounting().active:
                job.terminate()
        for child in self.children.values():
            child.kill()
            child.wait()
        self.deadline = time.monotonic() + win.TIMEOUT
        self.until(lambda: all(job.accounting().active == 0 and not win.members(job) for job in self.jobs.values()))
        self.assert_active("observer")
        self.ledger.add("unavailable", reason="deadline", subject_active=0, fixture_active=0,
                        outside_children_reaped=True, observer_survived=True)


def run_case(scenario, *, timeout_probe=False):
    require(scenario in SCENARIOS, "Unknown scenario")
    with TemporaryDirectory(prefix="wpai-split-route-") as directory:
        root = Path(directory)
        win.protect_scratch(root)
        fixture = prepare(root / "fixture")
        path = root / "witness.jsonl"
        with win.open_evidence(path) as writer, ExitStack() as jobs, ExitStack() as actors:
            scopes = {name: jobs.enter_context(win.Job(limit))
                      for name, limit in (("subject", 2), ("fixture", 1), ("force_guard", 1))}
            observer = Observer(Ledger(writer), root, fixture, actors, scopes)
            try:
                observer.run(scenario, timeout_probe)
            except TimeoutError:
                observer.recover_timeout()
            finally:
                for job in scopes.values():
                    if job.accounting().active:
                        job.terminate()
        data = path.read_bytes()
    return data, validate(data)

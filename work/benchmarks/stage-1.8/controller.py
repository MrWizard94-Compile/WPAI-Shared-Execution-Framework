"""Coordinate the frozen Stage 1.6 actors under witness acknowledgements."""

from contextlib import ExitStack
from pathlib import Path
import sys
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boundary import (CASES, CONTROLLER_MASKS, RUN_SECONDS, checked_jobs, deny_network, receive, received,
                      restrict_controller_launches, send, win)
from contract import require
from observer import Observer as Stage16Coordinator
from witness import REQUEST_HOPS


class Reporter:
    """Forward fixed control packets. The controller never opens the evidence writer."""

    def __init__(self, out, acknowledgements):
        self.out, self.acks = out, win.Reader(acknowledgements)
        self.deadline = time.monotonic() + RUN_SECONDS
        self.run = uuid4().hex
        self.coordinator = None

    def exchange(self, kind, **fields):
        send(self.out, kind=kind, **fields)
        require(receive(self.acks, self.deadline) == {"status": "durable"}, "Witness acknowledgment unavailable")

    def add(self, event, **fields):
        if event == "registered":
            role = fields["role"]
            real = self.coordinator.processes[role].identity
            self.exchange("registration", role=role, pid=real.pid, created=real.created)
        else:
            self.exchange("trace", row={"event": event, **fields})


class Coordinator(Stage16Coordinator):
    """Reuse Stage 1.6's actor control, transaction and graceful teardown."""

    def start_fixture(self, split_request, split_response, release):
        server_input, server_writer = self.pipe()
        assignment = self.own(win.copy_handle(self.jobs["fixture"].handle, 1))
        handles = [self.control("owner"), self.mailbox("owner"), split_request, split_response,
                   server_input, server_writer, self.mailbox("server"), assignment]
        self.direct("owner", handles, args=(str(self.fixture),)).start()
        self.attach_reported("server", "owner")
        self.job("fixture", "startup", ["server"])
        self.ledger.exchange("fixture_gate", released=release)
        if release:
            self.send("owner", "start_server")
            self.packet("server", "ready")
            self.ledger.exchange("fixture_ready")

    def start_subject(self, relay_writer, relay_reader):
        handles = [self.control("root"), self.mailbox("root"), relay_writer, relay_reader, self.mailbox("relay")]
        self.direct("root", handles, job_handle=self.jobs["subject"].handle).start()
        self.send("root", "spawn_relay")
        self.attach_reported("relay", "root")
        self.job("subject", "startup", ["root", "relay"])
        self.ledger.exchange("subject_gate")
        self.send("root", "start_relay")
        self.packet("relay", "ready")
        self.ledger.exchange("actors_ready")

    def begin_held_transaction(self):
        self.send("root", "request")
        for boundary in REQUEST_HOPS[:3]:
            row = self.packet(boundary.split("_", 1)[0], "wire", "bytes", "sha256", boundary=boundary)
            self.ledger.add("wire", **row)
        # The fixture owner has never received its release command and cannot read the split pipe.


def run(case, scratch, handles, stack):
    out, in_, *job_handles = handles
    jobs = checked_jobs(job_handles, CONTROLLER_MASKS)
    reporter = Reporter(out, in_)
    for name in ("write-canary", "witness.jsonl"):
        try:
            with (scratch / "journal" / name).open("r+b"):
                raise ValueError("Controller acquired write access to protected evidence storage")
        except PermissionError:
            pass
    reporter.exchange("protected_storage", canary_write_denied=True, journal_write_denied=True)
    if case == "before_launch":
        reporter.exchange("checkpoint", case=case)
        raise RuntimeError("A fault checkpoint must never resume")
    coordinator = Coordinator(reporter, scratch, scratch / "fixture" / "server", stack, jobs)
    reporter.coordinator = coordinator
    split_request, relay_writer = coordinator.pipe()
    relay_reader, split_response = coordinator.pipe()
    coordinator.start_fixture(split_request, split_response, release=case != "in_flight")
    coordinator.start_subject(relay_writer, relay_reader)
    if case == "actors_verified":
        reporter.exchange("checkpoint", case=case)
        raise RuntimeError("A fault checkpoint must never resume")
    if case == "in_flight":
        coordinator.begin_held_transaction()
        reporter.exchange("checkpoint", case=case)
        raise RuntimeError("A fault checkpoint must never resume")
    coordinator.transaction()
    if case == "response_verified":
        reporter.exchange("checkpoint", case=case)
        raise RuntimeError("A fault checkpoint must never resume")
    coordinator.graceful_fixture("normal")


def main():
    case, scratch, *values = sys.argv[1:]
    require(case in CASES, "Unknown controller case")
    deny_network()
    restrict_controller_launches()
    with ExitStack() as handles:
        inherited = received(handles, values, 4)
        with ExitStack() as actors:
            run(case, Path(scratch), inherited, actors)
        # Normal completion is reported after the inherited actor handles have settled and closed.
        Reporter(inherited[0], inherited[1]).exchange("finish")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

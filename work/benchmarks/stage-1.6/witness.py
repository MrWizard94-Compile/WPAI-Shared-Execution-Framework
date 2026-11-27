"""Stage 1.6 versioned, canonical witness ledger and scenario evidence rules."""

import os
import re
import time
from uuid import uuid4

from contract import REQUEST, RESPONSE_MARK, RESULTS, SCENARIOS, canonical, digest, observation, parse, require


SCHEMA = "wpai.benchmark.split-route-witness.v1"
LIMIT = 96
LINE_BYTES = 1024
INITIAL = "0" * 64
FORCED = 124
OWNER_LOST = 125
DUPLICATE_WINDOW_MS = 120
REQUEST_HOPS = ("root_request_write", "relay_request_read", "relay_request_write", "owner_request_read",
                "owner_request_write", "server_request_read")
RESPONSE_HOPS = ("server_response_write", "owner_response_read", "owner_response_write", "relay_response_read",
                 "relay_response_write", "root_response_read")
READERS = {
    "front_request": "relay", "front_response": "root", "split_request": "owner", "split_response": "relay",
    "fixture_request": "server", "fixture_response": "owner", "owner_control": "observer",
}
MEMBERSHIP = {"observer": "outside", "owner": "outside", "server": "fixture",
              "root": "subject", "relay": "subject", "force": "outside"}
TOKEN = re.compile("[a-f0-9]{64}")
RUN = re.compile("[a-f0-9]{32}")
TIMEOUT_RECORD = {"event": "unavailable", "reason": "deadline", "subject_active": 0, "fixture_active": 0,
                  "outside_children_reaped": True, "observer_survived": True}


def token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


def seal(content):
    return {**content, "hash": digest(canonical(content))}


class Ledger:
    """The caller provides a Win32 exclusive, noninheritable writer."""

    def __init__(self, writer):
        self.writer = writer
        self.run = uuid4().hex
        self.previous = INITIAL
        self.seq = 0
        self.origin = time.monotonic_ns()

    def add(self, event, **fields):
        self.seq += 1
        require(self.seq <= LIMIT, "Ledger event limit")
        content = {"run": self.run, "seq": self.seq, "ns": time.monotonic_ns() - self.origin,
                   "prev": self.previous, "event": event, **fields}
        row = seal(content)
        line = canonical(row) + b"\n"
        require(len(line) <= LINE_BYTES, "Ledger line limit")
        if self.writer.write(line) != len(line):
            raise OSError("Short durable ledger write")
        self.writer.flush()
        os.fsync(self.writer.fileno())
        self.previous = row["hash"]


def rows(data):
    require(len(data) <= LIMIT * LINE_BYTES, "Ledger byte limit")
    lines = data.split(b"\n")
    truncated = lines.pop() != b""
    require(len(lines) <= LIMIT, "Ledger event limit")
    previous, timestamp, run = INITIAL, -1, None
    content = []
    for seq, line in enumerate(lines, 1):
        require(0 < len(line) < LINE_BYTES, "Ledger line limit")
        row = parse(line)
        require(isinstance(row, dict) and canonical(row) == line, "Noncanonical ledger line")
        hashed = row.pop("hash")
        require(token(hashed) and digest(canonical(row)) == hashed, "Ledger hash mismatch")
        require(type(row.get("seq")) is int and row["seq"] == seq and row["prev"] == previous,
                "Ledger sequence or chain mismatch")
        require(isinstance(row["run"], str) and RUN.fullmatch(row["run"]) and row["run"] == (run or row["run"]),
                "Ledger run mismatch")
        require(type(row["ns"]) is int and row["ns"] >= 0 and row["ns"] >= timestamp, "Ledger time went backwards")
        timestamp, previous, run = row.pop("ns"), hashed, row.pop("run")
        del row["prev"], row["seq"]
        content.append((row, timestamp))
    return content, truncated


class Contract:
    """Each scenario consumes a causal sequence of strict event shapes."""

    def __init__(self, events):
        self.events = events
        self.index = 0
        self.roles = {}
        self.creation = set()
        self.wire = {}
        self.codes = {}
        self.reads = {}
        self.missing = {}
        self.closures = []
        self.accounting = {}

    def expect(self, event, **fields):
        if self.index == len(self.events):
            raise EOFError("Missing required event")
        row, ns = self.events[self.index]
        if canonical(row) == canonical(TIMEOUT_RECORD):
            require(self.index == len(self.events) - 1, "Events after unavailable outcome")
            raise TimeoutError("Bounded observation unavailable")
        require(row.keys() == {"event", *fields} and row["event"] == event,
                f"Unexpected event at {self.index + 1}, expected {event}")
        for key, expected in fields.items():
            value = row[key]
            match = expected(value) if callable(expected) else type(value) is type(expected) and value == expected
            require(match, f"Invalid {event}.{key}")
        self.index += 1
        return row, ns

    def register(self, role):
        row, _ = self.expect("registered", role=role, job=MEMBERSHIP[role], process=token, creation=token,
                             method="retained_creation_handle")
        require(row["process"] not in self.roles.values() and row["creation"] not in self.creation,
                "Duplicate process or creation identity")
        self.roles[role] = row["process"]
        self.creation.add(row["creation"])

    def active(self, role, phase):
        self.expect("active", role=role, process=self.roles[role], phase=phase, job=MEMBERSHIP[role],
                    method="WaitForSingleObject+IsProcessInJob")

    def exit(self, role, code):
        self.expect("signaled", role=role, process=self.roles[role], method="WaitForSingleObject")
        self.expect("exit", role=role, process=self.roles[role], code=code, method="GetExitCodeProcess")
        self.codes[role] = code

    def job(self, job, phase, members):
        row, _ = self.expect("job", job=job, phase=phase, members=sorted(members),
                             active=len(members), total=2 if job == "subject" else 1,
                             method="QueryInformationJobObject")
        self.accounting[f"{job}_{phase}"] = {key: row[key] for key in ("members", "active", "total")}

    def read(self, channel):
        row, _ = self.expect("terminal_read", channel=channel, reader=READERS[channel], method="ReadFile",
                             status=lambda value: type(value) is int and value in (0, 38, 109), bytes=0)
        self.reads[channel] = row["status"]

    def close(self, channel, writer, method="CloseHandle"):
        _, ns = self.expect("writer_close", channel=channel, writer=writer, method=method)
        self.closures.append({"channel": channel, "writer": writer, "method": method})
        return ns

    def unavailable(self, channel):
        self.expect("read_unavailable", channel=channel, reader=READERS[channel], reason="reader_terminated")
        self.missing[channel] = "reader_terminated"

    def frames(self):
        for boundary in (*REQUEST_HOPS, *RESPONSE_HOPS):
            if boundary == RESPONSE_HOPS[0]:
                self.expect("server_read_waiting", actor="server")
            row, _ = self.expect("wire", boundary=boundary, bytes=lambda value: type(value) is int and 0 < value < 32768,
                                 sha256=token)
            actual = {key: row[key] for key in ("bytes", "sha256")}
            if boundary in REQUEST_HOPS:
                require(actual == observation(REQUEST), "Fixed request differs across hops")
                self.wire["request"] = actual
            else:
                require(actual == RESPONSE_MARK, "Frozen response differs across hops")
                self.wire["response"] = actual
        self.expect("oracle", actor="root", tool="repo_health_v1", facts=12, calls=1)

    def setup(self, scenario):
        self.expect("start", schema=SCHEMA, scenario=scenario)
        for role in ("observer", "owner", "server"):
            self.register(role)
        self.job("fixture", "startup", ["server"])
        self.expect("startup_gate", role="server")
        self.register("root")
        self.register("relay")
        self.job("subject", "startup", ["root", "relay"])
        self.expect("startup_gate", role="relay")
        if scenario in ("duplicate_writer", "owner_loss"):
            self.expect("writer_retained", channel="fixture_request",
                        writer="owner_duplicate" if scenario == "duplicate_writer" else "observer_guard")
        self.frames()

    def forced(self):
        self.register("force")
        self.expect("force_isolated", actor="force", integrity="low", storage_read_denied=True,
                    storage_write_denied=True, job_right="JOB_OBJECT_TERMINATE")
        self.active("root", "before_force")
        self.active("relay", "before_force")
        self.expect("force_request", target="subject", actor="observer")
        self.expect("force_ack", target="subject", actor="force", method="TerminateJobObject")
        self.exit("force", 0)
        self.exit("root", FORCED)
        self.exit("relay", FORCED)
        self.job("subject", "final", [])
        for role in ("owner", "server", "observer"):
            self.active(role, "after_subject_force")
        self.job("fixture", "after_subject_force", ["server"])
        self.close("split_request", "relay", "process_terminated")
        self.unavailable("front_request")
        self.unavailable("front_response")

    def owner_lost(self):
        self.active("owner", "before_loss")
        self.expect("owner_stop", actor="observer", method="TerminateProcess")
        self.exit("owner", OWNER_LOST)
        self.read("owner_control")
        self.expect("owner_lost", source="retained_handle_and_control_ReadFile")
        self.active("observer", "after_owner_loss")
        self.active("server", "after_owner_loss")
        self.job("fixture", "after_owner_loss", ["server"])
        for job, roles in (("fixture", ("server",)), ("subject", ("root", "relay"))):
            self.expect("recovery_force", target=job, actor="observer", method="TerminateJobObject")
            for role in roles:
                self.exit(role, FORCED)
            self.job(job, "final", [])
        self.close("fixture_request", "observer_guard")
        for channel in READERS:
            if channel != "owner_control":
                self.unavailable(channel)

    def graceful_fixture(self, scenario):
        forced = scenario == "external_termination"
        if forced:
            self.forced()
        else:
            self.close("front_request", "root")
            self.read("front_request")
            self.close("split_request", "relay")
        self.read("split_request")
        self.close("split_response", "owner")
        if forced:
            self.unavailable("split_response")
        else:
            self.read("split_response")
            self.close("front_response", "relay")
            self.read("front_response")
            self.exit("relay", 0)
            self.exit("root", 0)
            self.job("subject", "final", [])
        closed = self.close("fixture_request", "owner_primary")
        if scenario == "duplicate_writer":
            self.active("server", "duplicate_open")
            _, ns = self.expect("still_open", channel="fixture_request", result="no_terminal_report",
                                window_ms=DUPLICATE_WINDOW_MS)
            require(ns - closed >= DUPLICATE_WINDOW_MS * 1_000_000, "Duplicate observation window too short")
            self.close("fixture_request", "owner_duplicate")
        self.read("fixture_request")
        self.expect("server_empty_read", actor="server", bytes=0)
        self.close("fixture_response", "server", "CRT_close")
        self.read("fixture_response")
        self.exit("server", 0)
        self.exit("owner", 0)
        self.job("fixture", "final", [])

    def validate(self, scenario):
        self.setup(scenario)
        if scenario == "owner_loss":
            self.owner_lost()
        else:
            self.graceful_fixture(scenario)
        self.expect("finalized", actor="observer", process=self.roles["observer"], job="outside")
        require(self.index == len(self.events), "Events after observer finalization")
        lifecycle, qualification = RESULTS[scenario]
        return {"lifecycle": lifecycle, "qualification": qualification,
                "exit_codes": self.codes, "ReadFile_terminal_status": self.reads,
                "unavailable_reads": self.missing, "writer_closes": self.closures,
                "job_accounting": self.accounting, "wire": self.wire, "observer_finalized": True,
                "server_empty_read_attested": scenario != "owner_loss",
                "force_isolation_probe": "read_and_write_denied" if scenario == "external_termination" else None,
                "duplicate_writer_window_ms": DUPLICATE_WINDOW_MS if scenario == "duplicate_writer" else None}


def validate(data):
    try:
        events, truncated = rows(data)
        if not events:
            return {"lifecycle": "incomplete", "reason": "no_complete_record"}
        scenario = events[0][0].get("scenario")
        require(scenario in SCENARIOS, "Invalid scenario")
        outcome = Contract(events).validate(scenario)
        if truncated:
            return {"lifecycle": "incomplete", "reason": "truncated_record"}
        return outcome
    except EOFError:
        return {"lifecycle": "incomplete", "reason": "truncated_record" if truncated else "missing_event"}
    except TimeoutError:
        if truncated:
            return {"lifecycle": "incomplete", "reason": "truncated_record"}
        return {"lifecycle": "unavailable", "reason": "deadline", "bounded_recovery": True}
    except (ValueError, KeyError, TypeError, RecursionError) as error:
        return {"lifecycle": "invalid", "reason": str(error)}

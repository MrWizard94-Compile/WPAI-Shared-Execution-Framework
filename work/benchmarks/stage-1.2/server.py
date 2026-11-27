"""Child process entry point for the two synthetic arms."""

from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import threading
import time

import wpai_exec as app


PROJECT = "fictional-clockwork-museum"
CLOCK = "2034-06-18T12:00:00.000Z"
CONTROL = "fixture_read_field_v1"


def protect(event, _args):
    if event == "open" or event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn", "os.system")):
        raise PermissionError("Benchmark fixture prohibits external acquisition")


class Trace:
    def __init__(self, stream, arm):
        self.stream = stream
        self.arm = arm
        self.started = time.perf_counter_ns()
        self.lock = threading.Lock()
        self.requests = {}
        self.count = 0
        self.protocol = None

    def event(self, event, **fields):
        with self.lock:
            self.count += 1
            if self.count <= 512:
                self.stream.write(json.dumps({"event": event, "ms_from_server_start": self.ms(self.started), **fields}) + "\n")
                self.stream.flush()

    @staticmethod
    def ms(start):
        return round((time.perf_counter_ns() - start) / 1_000_000, 4)


class Input:
    def __init__(self, stream, trace):
        self.stream, self.trace = stream, trace

    def readline(self, size):
        line = self.stream.readline(size)
        if line.endswith(b"\n"):
            try:
                wire = json.loads(line)
                method = wire.get("method")
                params = wire.get("params", {})
                if method in ("initialize", "server/discover", "tools/list", "tools/call") and "id" in wire:
                    with self.trace.lock:
                        if len(self.trace.requests) < 128:
                            self.trace.requests[wire["id"]] = (method, time.perf_counter_ns())
                    self.trace.event("received", method=method)
                if method == "server/discover" or params.get("_meta", {}).get(app.META + "protocolVersion") == app.MODERN:
                    self.trace.protocol = app.MODERN
            except (ValueError, TypeError, AttributeError, RecursionError):
                pass
        return line


class Output:
    def __init__(self, stream, trace):
        self.stream, self.trace = stream, trace
        self.line = bytearray()

    def write(self, data):
        self.line.extend(data)
        count = self.stream.write(data)
        del self.line[len(self.line) - len(data) + count:]
        if self.line.endswith(b"\n"):
            wire = json.loads(self.line)
            with self.trace.lock:
                observed = self.trace.requests.pop(wire.get("id"), None)
            if observed:
                method, arrived = observed
                body = wire.get("result", {})
                if method == "initialize":
                    self.trace.protocol = body.get("protocolVersion")
                text = body.get("content", [{}])[0].get("text", "")
                self.trace.event("sent", method=method, protocol=self.trace.protocol,
                                 ok="error" not in wire and not body.get("isError"),
                                 round_trip_ms=self.trace.ms(arrived), wire_bytes=len(self.line),
                                 report_json_bytes=len(text.encode()),
                                 report_sha256=sha256(text.encode()).hexdigest() if text else None,
                                 parity=json.loads(text) == body.get("structuredContent") if text else None)
            self.line.clear()
        return count

    def flush(self):
        self.stream.flush()


def install(arm, facts, trace):
    app.PROJECT = PROJECT
    if arm == "control":
        app.TOOL = CONTROL
        app.TOOL_SPEC = {
            "name": CONTROL, "description": "Return exactly one fact from a fixed fictional benchmark dataset.",
            "inputSchema": {"type": "object", "properties": {"field": {"type": "string", "enum": list(facts)}},
                            "required": ["field"], "additionalProperties": False},
            "outputSchema": {"type": "object", "required": ["contract", "status"]},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
        }
    else:
        app.TOOL_SPEC = {**app.TOOL_SPEC,
                         "description": "Return the complete repository-health report for a fixed fictional benchmark dataset.",
                         "inputSchema": {**app.TOOL_SPEC["inputSchema"],
                                         "properties": {"project": {"type": "string", "enum": [PROJECT]}}},
                         "annotations": {**app.TOOL_SPEC["annotations"], "openWorldHint": False}}

    def health(arguments, cancellation=None):
        started = time.perf_counter_ns()
        key = "field" if arm == "control" else "project"
        value = arguments.get(key)
        payload = {"contract": "wpai.benchmark.field.v1" if arm == "control" else app.CONTRACT}
        field = value if isinstance(value, str) and value in facts else None
        if set(arguments) != {key} or not isinstance(value, str):
            payload["status"] = "INVALID_ARGUMENTS"
        elif arm == "control" and field:
            payload.update(status="OK", field=field, fact=facts[field])
        elif arm == "treatment" and value == PROJECT:
            payload.update(status="OK", project=PROJECT, opened_at=CLOCK, closed_at=CLOCK,
                           facts=facts, measurements={"elapsed_ms": 0, "git_process_attempts": 0,
                                                      "github_get_process_attempts": 0, "provider_usage": "unavailable"})
        else:
            payload["status"] = "DENIED"
        trace.event("acquisition", tool=app.TOOL, field=field if arm == "control" else None,
                    status=payload["status"], acquisition_ms=trace.ms(started), process_attempts=0)
        return payload

    compact = app.compact

    def measured_compact(value):
        started = time.perf_counter_ns()
        text = compact(value)
        trace.event("serialization", scope="envelope" if "jsonrpc" in value else "payload",
                    serialization_ms=trace.ms(started))
        return text

    app.health = health
    app.compact = measured_compact


def main():
    arm, log = sys.argv[1:]
    if arm not in ("control", "treatment"):
        return 2
    facts = json.loads(Path(__file__).with_name("ground_truth.json").read_bytes())["facts"]
    with open(log, "x", encoding="utf-8", newline="\n") as stream:
        trace = Trace(stream, arm)
        trace.event("start", pid=os.getpid(), arm=arm)
        install(arm, facts, trace)
        sys.addaudithook(protect)
        incoming, outgoing = sys.stdin.buffer, sys.stdout.buffer
        transport = app.Stdio(Input(getattr(incoming, "raw", incoming), trace),
                              Output(getattr(outgoing, "raw", outgoing), trace))
        code = transport.serve()
        trace.event("stop", code=code, worker_alive=bool(transport.worker and transport.worker.is_alive()))
        return code


if __name__ == "__main__":
    raise SystemExit(main())

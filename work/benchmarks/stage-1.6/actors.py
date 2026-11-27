"""Fixed synthetic actors. Data and observer control travel over distinct anonymous pipes."""

from contextlib import ExitStack
import ctypes as c
import importlib
import msvcrt
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))  # Absolute source under isolated Python.
import win
from contract import DATASET_HASH, REQUEST, canonical, digest, observation, parse, require, verify_response


def report(handle, event, **fields):
    win.write(handle.value, canonical({"event": event, **fields}) + b"\n")


def command(reader, expected):
    require(reader.line() == expected.encode("ascii") + b"\n", "Unexpected or lost control command")


def child_identity(handle, role, child):
    created = win.identity(child.process.value)
    report(handle, "created", role=role, pid=created.pid, created=created.created)


def transfer(data, destination, telemetry, direction):
    report(telemetry, "wire", boundary=direction + "_read", **observation(data))
    win.write(destination.value, data)
    report(telemetry, "wire", boundary=direction + "_write", **observation(data))


def terminal(reader, telemetry, channel):
    require(reader.line() == b"" and reader.terminal in (0, 38, 109), "Expected terminal ReadFile")
    report(telemetry, "read_terminal", channel=channel, status=reader.terminal)


def close_writer(handle, telemetry, channel, writer):
    handle.close()
    report(telemetry, "writer_closed", channel=channel, writer=writer)


def subject(handles):
    gate, telemetry, owner_input, owner_output, relay_telemetry = handles
    control = win.Reader(gate.value)
    command(control, "spawn_relay")
    with ExitStack() as stack:
        front_input, root_writer = win.pipe()
        root_reader, front_output = win.pipe()
        for handle in (front_input, root_writer, root_reader, front_output):
            stack.callback(handle.close)
        child = win.spawn("relay", [front_input, front_output, owner_input, owner_output, relay_telemetry])
        stack.callback(child.close)
        for handle in (front_input, front_output, owner_input, owner_output, relay_telemetry):
            handle.close()
        child_identity(telemetry, "relay", child)
        command(control, "start_relay")
        child.start()
        command(control, "request")
        win.write(root_writer.value, REQUEST)
        report(telemetry, "wire", boundary="root_request_write", **observation(REQUEST))
        returned = win.Reader(root_reader.value)
        payload = returned.line()
        verify_response(payload)
        report(telemetry, "wire", boundary="root_response_read", **observation(payload))
        report(telemetry, "oracle_exact")
        command(control, "close_root")
        close_writer(root_writer, telemetry, "front_request", "root")
        terminal(returned, telemetry, "front_response")
        child.wait()
    return 0


def relay(handles):
    front_input, front_output, owner_input, owner_output, telemetry = handles
    report(telemetry, "ready")
    incoming, returned = win.Reader(front_input.value), win.Reader(owner_output.value)
    payload = incoming.line()
    require(payload == REQUEST, "Unexpected relay request")
    transfer(payload, owner_input, telemetry, "relay_request")
    transfer(returned.line(), front_output, telemetry, "relay_response")
    terminal(incoming, telemetry, "front_request")
    close_writer(owner_input, telemetry, "split_request", "relay")
    terminal(returned, telemetry, "split_response")
    close_writer(front_output, telemetry, "front_response", "relay")
    return 0


def owner(handles, fixture):
    gate, telemetry, split_input, split_output, server_input, server_writer, server_telemetry, job, *extra = handles
    ctrl = win.Reader(gate.value)
    with ExitStack() as stack:
        server_return, server_stdout = win.pipe()
        stack.callback(server_return.close)
        stack.callback(server_stdout.close)
        child = win.spawn("server", [server_telemetry], args=(fixture,),
                          stdio=(server_input.value, server_stdout.value), job_handle=job.value)
        stack.callback(child.close)
        for handle in (server_input, server_stdout, server_telemetry, job):
            handle.close()
        child_identity(telemetry, "server", child)
        command(ctrl, "start_server")
        child.start()
        incoming, response = win.Reader(split_input.value), win.Reader(server_return.value)
        payload = incoming.line()
        require(payload == REQUEST, "Unexpected fixture owner request")
        transfer(payload, server_writer, telemetry, "owner_request")
        result = response.line()
        transfer(result, split_output, telemetry, "owner_response")
        command(ctrl, "check_split_input")
        terminal(incoming, telemetry, "split_request")
        close_writer(split_output, telemetry, "split_response", "owner")
        command(ctrl, "close_primary")
        close_writer(server_writer, telemetry, "fixture_request", "owner_primary")
        if extra:
            command(ctrl, "close_duplicate")
            close_writer(extra[0], telemetry, "fixture_request", "owner_duplicate")
        command(ctrl, "drain")
        terminal(response, telemetry, "fixture_response")
        child.wait()
    return 0


class AuditedInput:
    """Attest an actual empty ReadFile result at the packaged server's input reader."""

    def __init__(self, telemetry, waiting):
        self.pipe = win.Reader(msvcrt.get_osfhandle(0))
        self.telemetry = telemetry
        self.frames = 0
        self.waiting = waiting

    def readline(self, size):
        if self.frames:
            report(self.telemetry, "server_read_waiting")
            self.waiting.set()
            terminal(self.pipe, self.telemetry, "fixture_request")
            report(self.telemetry, "server_empty_read")
            return b""
        frame = self.pipe.line()
        require(frame == REQUEST and len(frame) <= size, "Fixture read mismatched fixed request")
        self.frames += 1
        report(self.telemetry, "wire", boundary="server_request_read", **observation(frame))
        return frame


class AuditedOutput:
    def __init__(self, telemetry, waiting):
        self.telemetry = telemetry
        self.sent = False
        self.waiting = waiting

    def write(self, frame):
        require(not self.sent, "Fixture wrote more than one response")
        require(self.waiting.wait(win.TIMEOUT), "Fixture never entered its next read")
        self.sent = True
        win.write(msvcrt.get_osfhandle(1), bytes(frame))
        report(self.telemetry, "wire", boundary="server_response_write", **observation(frame))
        return len(frame)

    def flush(self):
        pass  # WriteFile is synchronous and unbuffered here.


def server(handles, fixture):
    telemetry, = handles
    root = Path(fixture)
    dataset = (root / "ground_truth.json").read_bytes()
    require(digest(dataset) == DATASET_HASH, "Server fixture identity differs")
    sys.path.insert(0, str(root))
    stage12 = importlib.import_module("server")
    trace = stage12.Trace(None, "treatment")
    trace.event = lambda *_args, **_fields: None
    stage12.install("treatment", parse(dataset)["facts"], trace)
    sys.addaudithook(stage12.protect)
    report(telemetry, "ready")
    waiting = threading.Event()
    code = stage12.app.Stdio(AuditedInput(telemetry, waiting), AuditedOutput(telemetry, waiting)).serve()
    os.close(1)
    report(telemetry, "writer_closed", channel="fixture_response", writer="server")
    return code


def force(handles, canary):
    gate, telemetry, job = handles
    for mode in ("rb", "ab"):
        try:
            with open(canary, mode):
                raise ValueError("Force process obtained protected run storage")
        except PermissionError:
            pass
    report(telemetry, "isolation_denied", read=True, write=True)

    def prohibit(event, _args):
        if event == "open" or event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn", "os.system")):
            raise PermissionError("Force controller can only terminate the provided job")

    sys.addaudithook(prohibit)
    command(win.Reader(gate.value), "force")
    win.checked(win.terminate_job(job.value, win.FORCED))
    report(telemetry, "force_ack")
    return 0


def main():
    role, *values = sys.argv[1:]
    runner = {"subject": subject, "relay": relay, "owner": owner, "server": server, "force": force}[role]
    args = (values.pop(),) if role in ("owner", "server", "force") else ()

    def local_only(event, _args):
        if event.startswith("socket."):
            raise PermissionError("Synthetic actors have no network route")

    sys.addaudithook(local_only)
    with ExitStack() as stack:
        handles = []
        for value in values:
            handle = win.Handle(int(value))
            os.set_handle_inheritable(handle.value, False)
            stack.callback(handle.close)
            handles.append(handle)
        return runner(handles, *args)


if __name__ == "__main__":
    raise SystemExit(main())

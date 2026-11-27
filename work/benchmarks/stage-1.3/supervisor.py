"""Own a trusted synthetic worker and transport stdio as uninterpreted bytes."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time

import winjob


SCHEMA = "wpai.benchmark.lifecycle.v1"
BOOTSTRAP = Path(__file__).resolve().with_name("bootstrap.py")
CHUNK = 4096


@dataclass(frozen=True)
class Limits:
    timeout: float = 60
    eof_grace: float = 2
    cleanup_grace: float = 3
    diagnostic_bytes: int = 4096


def read_chunk(stream):
    return getattr(stream, "read1", stream.read)(CHUNK)


def write_all(stream, data):
    pending = memoryview(data)
    while pending:
        count = stream.write(pending)
        if not isinstance(count, int) or not 0 < count <= len(pending):
            raise BrokenPipeError("stream made no forward progress")
        pending = pending[count:]


class Pump:
    def __init__(self, action, name, faults):
        self.stop = threading.Event()
        self.done = threading.Event()
        self.handle = None

        def run():
            try:
                self.handle = winjob.checked(winjob.open_thread(0x0001, False, threading.get_native_id()))
                action(self.stop)
            except (OSError, ValueError, RuntimeError):
                if not self.stop.is_set():
                    faults.append(name)
            finally:
                self.done.set()

        self.thread = threading.Thread(target=run, name=name, daemon=True)
        self.thread.start()

    def interrupt(self):
        self.stop.set()
        if self.handle and not self.done.is_set():
            # Cancel only this pump's currently pending synchronous I/O.
            winjob.cancel_io(self.handle)

    def close(self):
        if self.handle:
            winjob.close_handle(self.handle)


def forward(client_stdin, client_stdout, script, arguments=(), *, limits=Limits(), cancel=None):
    """Return sanitized lifecycle evidence and a separate capped private stderr buffer."""
    started = time.monotonic()
    stop_request = cancel if cancel is not None else threading.Event()
    if not all(0 < value < 3600 for value in (limits.timeout, limits.eof_grace, limits.cleanup_grace)):
        raise ValueError("Expected finite positive time limits below one hour")
    if not 0 <= limits.diagnostic_bytes <= 64 * 1024:
        raise ValueError("Diagnostic limit is outside the supported range")
    diagnostic = bytearray()
    faults = []
    counts = {"input": 0, "output": 0, "stderr": 0}
    flags = {"client_stdin_eof": False, "stdin_closed": False, "stdin_closed_at": None}
    with TemporaryDirectory(prefix="wpai-lifecycle-") as private, winjob.Job() as job:
        marker = Path(private) / "observed-eof"
        argv = [sys.executable, "-I", "-S", "-B", "-W", "error", str(BOOTSTRAP),
                str(Path(script).resolve()), str(marker), *arguments]
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        pumps = []
        attached = False
        forced_reason = None
        terminal = None
        try:
            job.assign(child.pid)
            attached = True
            write_all(child.stdin, b"\x01")

            def input_bytes(stop):
                try:
                    while not stop.is_set():
                        data = read_chunk(client_stdin)
                        if stop.is_set():
                            break
                        if not data:
                            flags["client_stdin_eof"] = True
                            break
                        write_all(child.stdin, data)
                        counts["input"] += len(data)
                finally:
                    child.stdin.close()
                    flags.update(stdin_closed=True, stdin_closed_at=time.monotonic())

            def output_bytes(stop):
                while not stop.is_set():
                    data = read_chunk(child.stdout)
                    if not data or stop.is_set():
                        break
                    write_all(client_stdout, data)
                    client_stdout.flush()
                    counts["output"] += len(data)

            def stderr_bytes(stop):
                while not stop.is_set():
                    data = read_chunk(child.stderr)
                    if not data:
                        break
                    counts["stderr"] += len(data)
                    diagnostic.extend(data[:max(0, limits.diagnostic_bytes - len(diagnostic))])

            pumps = [Pump(action, name, faults) for action, name in (
                (input_bytes, "stdin_pipe_error"), (output_bytes, "stdout_pipe_error"), (stderr_bytes, "stderr_pipe_error"))]
            deadline = started + limits.timeout
            wait_reason = None
            wait_until = None
            exit_seen = None
            while True:
                now = time.monotonic()
                code = child.poll()
                active = job.accounting().active
                if code is not None and active == 0:
                    terminal = "child_exited"
                    break
                if code is not None and exit_seen is None:
                    exit_seen = now
                if wait_reason is None:
                    if stop_request.is_set():
                        wait_reason = "cancelled"
                    elif faults:
                        wait_reason = faults[0]
                    elif exit_seen is not None:
                        wait_reason = "descendants_after_exit"
                    elif flags["stdin_closed_at"] is not None:
                        wait_reason = "stdin_eof_timeout"
                    if wait_reason:
                        wait_until = (flags["stdin_closed_at"] if wait_reason == "stdin_eof_timeout" else now) + limits.eof_grace
                if wait_reason in ("cancelled", "stdout_pipe_error", "stderr_pipe_error"):
                    pumps[0].interrupt()
                if now >= deadline or (wait_until is not None and now >= wait_until):
                    forced_reason = wait_reason if wait_until is not None and wait_until <= deadline else "timeout"
                    job.terminate()
                    terminal = "job_terminated"
                    break
                time.sleep(0.005)

            # The client may still own an open input pipe even when its server has exited.
            pumps[0].interrupt()
            cleanup_deadline = time.monotonic() + limits.cleanup_grace
            child.wait(timeout=limits.cleanup_grace)
            while job.accounting().active and time.monotonic() < cleanup_deadline:
                time.sleep(0.005)
            while not all(pump.done.is_set() for pump in pumps) and time.monotonic() < cleanup_deadline:
                pumps[0].interrupt()
                time.sleep(0.005)
            for pump in pumps:
                if not pump.done.is_set():
                    faults.append(pump.thread.name.removesuffix("_pipe_error") + "_drain_timeout")
                    while not pump.done.is_set() and time.monotonic() < cleanup_deadline + 0.5:
                        pump.interrupt()
                        pump.thread.join(0.01)
            accounting = job.accounting()
            observed = marker.exists() and marker.read_bytes() == b"observed\n"
            tree_gone = accounting.active == 0 and child.returncode is not None
            transport_ok = not faults and all(pump.done.is_set() for pump in pumps)
            record = {
                "schema": SCHEMA, "client_stdin_eof": flags["client_stdin_eof"],
                "child_stdin_closed": flags["stdin_closed"], "server_eof_observed": observed,
                "server_exit_code": child.returncode, "forced_termination": forced_reason is not None,
                "termination_reason": forced_reason or (
                    "cancelled" if stop_request.is_set() else faults[0] if faults else terminal),
                "process_tree_verified_gone": tree_gone, "processes_in_owned_job": accounting.total,
                "active_processes_at_check": accounting.active, "transport_ok": transport_ok,
                "transport_faults": faults, "stdin_bytes_forwarded": counts["input"], "stdout_bytes_forwarded": counts["output"],
                "stderr_bytes_seen": counts["stderr"], "stderr_bytes_retained": len(diagnostic),
                "stderr_truncated": counts["stderr"] > len(diagnostic), "elapsed_seconds": round(time.monotonic() - started, 6),
            }
            record["lifecycle_valid"] = (observed and record["client_stdin_eof"] and record["child_stdin_closed"]
                                         and child.returncode == 0
                                         and not record["forced_termination"] and tree_gone and transport_ok
                                         and not stop_request.is_set())
            return record, bytes(diagnostic)
        finally:
            if attached and job.accounting().active:
                job.terminate()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=limits.cleanup_grace)
            for pump in pumps:
                for _ in range(8):
                    if pump.done.is_set():
                        break
                    pump.interrupt()
                    pump.thread.join(0.01)
                pump.close()
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

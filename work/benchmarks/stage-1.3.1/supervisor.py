"""Own a trusted synthetic worker and transport stdio as uninterpreted bytes."""

from dataclasses import dataclass
from io import FileIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time

from lifecycle_receipt import PUMP_NAMES, SCHEMA
import winjob


BOOTSTRAP = Path(__file__).resolve().parents[1] / "stage-1.3" / "bootstrap.py"
CHUNK = 4096
POLL_SECONDS = 0.005


@dataclass(frozen=True)
class Limits:
    timeout: float = 60
    eof_grace: float = 2
    cleanup_grace: float = 3
    diagnostic_bytes: int = 4096


def read_chunk(stream):
    if isinstance(stream, FileIO):
        return winjob.read_pipe(stream, CHUNK)
    return getattr(stream, "read1", stream.read)(CHUNK)


def write_all(stream, data, stop=None):
    sent = 0
    pending = memoryview(data)
    while pending and (stop is None or not stop.is_set()):
        count = winjob.write_pipe(stream, pending) if isinstance(stream, FileIO) else stream.write(pending)
        if type(count) is not int or not 0 < count <= len(pending):
            raise BrokenPipeError("stream made no forward progress")
        sent += count
        pending = pending[count:]
    return sent


class Faults:
    def __init__(self):
        self._lock = threading.Lock()
        self._errors = {}

    def add(self, name, error=None):
        code = getattr(error, "winerror", None)
        with self._lock:
            self._errors.setdefault(name, code if type(code) is int and code > 0 else None)

    def snapshot(self):
        with self._lock:
            return dict(self._errors)


class Pump:
    def __init__(self, action, name, faults, close_stream):
        self.name = name
        self.stop = threading.Event()
        self.faults = faults
        self._handle_lock = threading.Lock()
        self._handle = None

        def run():
            try:
                with self._handle_lock:
                    self._handle = winjob.checked(winjob.open_thread(
                        winjob.THREAD_TERMINATE, False, threading.get_native_id()))
                if not self.stop.is_set():
                    action(self.stop)
            except (OSError, ValueError, RuntimeError) as error:
                if not (self.stop.is_set() and getattr(error, "winerror", None) == winjob.ERROR_OPERATION_ABORTED):
                    faults.add(f"{name}_pipe_error", error)
            finally:
                try:
                    close_stream()
                except OSError as error:
                    faults.add(f"{name}_stream_close_error", error)
                finally:
                    # Keep the handle valid for an in-flight cancel call, then close it
                    # on the owning thread after all pump I/O and stream work returned.
                    with self._handle_lock:
                        if self._handle is not None:
                            try:
                                winjob.checked(winjob.close_handle(self._handle))
                            except OSError as error:
                                faults.add(f"{name}_thread_handle_close_error", error)
                            self._handle = None

        self.thread = threading.Thread(target=run, name=f"wpai-stdio-{name}", daemon=True)
        self.thread.start()

    def interrupt(self):
        self.stop.set()
        with self._handle_lock:
            if self._handle is not None and self.thread.is_alive():
                try:
                    winjob.cancel_pending_io(self._handle)
                except OSError as error:
                    self.faults.add(f"{self.name}_cancel_error", error)


def await_pumps(pumps, deadline, *, interrupt_all=False):
    """Check thread termination and repeat cancellation across the I/O start race."""
    while remaining := [pump for pump in pumps if pump.thread.is_alive()]:
        if time.monotonic() >= deadline:
            break
        for pump in remaining:
            if interrupt_all or pump.name == "stdin":
                pump.interrupt()
        for pump in remaining:
            pump.thread.join(timeout=min(POLL_SECONDS, max(0, deadline - time.monotonic())))


def forward(client_stdin, client_stdout, script, arguments=(), *, limits=Limits(), cancel=None):
    """Return sanitized lifecycle evidence and a separate capped private stderr buffer."""
    started = time.monotonic()
    stop_request = cancel if cancel is not None else threading.Event()
    if not all(0 < value < 3600 for value in (limits.timeout, limits.eof_grace, limits.cleanup_grace)):
        raise ValueError("Expected finite positive time limits below one hour")
    if not 0 <= limits.diagnostic_bytes <= 64 * 1024:
        raise ValueError("Diagnostic limit is outside the supported range")
    diagnostic = bytearray()
    faults = Faults()
    counts = {"input": 0, "output": 0, "stderr": 0}
    input_eof = False
    stdin_closed_at = None
    with TemporaryDirectory(prefix="wpai-lifecycle-") as private, winjob.Job() as job:
        marker = Path(private) / "observed-eof"
        argv = [sys.executable, "-I", "-S", "-B", "-W", "error", str(BOOTSTRAP),
                str(Path(script).resolve()), str(marker), *arguments]
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        pumps = []
        attached = False
        forced = False
        forced_reason = None

        def account():
            try:
                return job.accounting()
            except OSError as error:
                faults.add("job_accounting_error", error)
                return None

        def terminate_tree():
            nonlocal forced
            try:
                job.terminate()
                forced = True
            except OSError as error:
                faults.add("job_termination_error", error)

        def input_bytes(stop):
            nonlocal input_eof
            while not stop.is_set():
                data = read_chunk(client_stdin)
                if stop.is_set():
                    break
                if not data:
                    input_eof = True
                    break
                counts["input"] += write_all(child.stdin, data, stop)

        def close_stdin():
            nonlocal stdin_closed_at
            child.stdin.close()
            stdin_closed_at = time.monotonic()

        def output_bytes(stop):
            while not stop.is_set():
                data = read_chunk(child.stdout)
                if not data or stop.is_set():
                    break
                counts["output"] += write_all(client_stdout, data, stop)
                if not stop.is_set():
                    client_stdout.flush()

        def stderr_bytes(stop):
            while not stop.is_set():
                data = read_chunk(child.stderr)
                if not data:
                    break
                counts["stderr"] += len(data)
                diagnostic.extend(data[:max(0, limits.diagnostic_bytes - len(diagnostic))])

        streams = dict(zip(PUMP_NAMES, (child.stdin, child.stdout, child.stderr)))
        try:
            job.assign(child.pid)
            attached = True
            write_all(child.stdin, b"\x01")
            for name, action, close_stream in (
                ("stdin", input_bytes, close_stdin), ("stdout", output_bytes, child.stdout.close),
                ("stderr", stderr_bytes, child.stderr.close),
            ):
                pumps.append(Pump(action, name, faults, close_stream))
            deadline = started + limits.timeout
            wait_reason = None
            wait_until = deadline
            while True:
                now = time.monotonic()
                code = child.poll()
                state = account()
                if state is None:
                    break
                if code is not None and state.active == 0:
                    break
                fault = next(iter(faults.snapshot()), None)
                abort = "cancelled" if stop_request.is_set() else fault
                if abort is not None:
                    # An earlier EOF grace can stay shorter. Each pump gets its own stop.
                    if wait_reason is None or wait_reason == "stdin_eof_timeout":
                        wait_reason = abort
                        wait_until = min(wait_until, now + limits.eof_grace)
                    for pump in pumps:
                        pump.interrupt()
                elif wait_reason is None:
                    if code is not None:
                        wait_reason = "descendants_after_exit"
                        wait_until = min(wait_until, now + limits.eof_grace)
                    elif stdin_closed_at is not None:
                        wait_reason = "stdin_eof_timeout"
                        wait_until = min(wait_until, stdin_closed_at + limits.eof_grace)
                if now >= wait_until:
                    forced_reason = wait_reason if wait_until < deadline else "timeout"
                    terminate_tree()
                    break
                time.sleep(POLL_SECONDS)
        finally:
            cleanup_started = time.monotonic()
            cleanup_deadline = cleanup_started + limits.cleanup_grace
            state = account() if attached else None
            if attached and not forced and (state is None or state.active or child.poll() is None):
                forced_reason = forced_reason or "cleanup_termination"
                terminate_tree()
            if not forced and child.poll() is None:
                try:
                    child.kill()
                    forced = True
                except OSError as error:
                    faults.add("child_kill_error", error)
            for name, stream in streams.items():
                if all(pump.name != name for pump in pumps):
                    try:
                        stream.close()
                    except OSError as error:
                        faults.add(f"{name}_stream_close_error", error)

            # Let pending output drain before requesting cancellation. Reserve time
            # for every still-live pump to observe its request and be joined.
            drain_deadline = cleanup_started + limits.cleanup_grace * 0.75
            await_pumps(pumps, drain_deadline)
            for pump in pumps:
                if pump.thread.is_alive():
                    faults.add(f"{pump.name}_drain_timeout")
                    pump.interrupt()
            await_pumps(pumps, cleanup_deadline, interrupt_all=True)
            try:
                child.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                faults.add("child_wait_timeout")
            state = account() if attached else None
            while state is not None and state.active and time.monotonic() < cleanup_deadline:
                time.sleep(POLL_SECONDS)
                state = account()
            if state is not None and state.active:
                faults.add("job_cleanup_incomplete")

        outstanding = [pump.name for pump in pumps if pump.thread.is_alive()]
        for name in outstanding:
            faults.add(f"{name}_thread_still_alive")
        all_stopped = len(pumps) == len(PUMP_NAMES) and not outstanding
        transport_faults = faults.snapshot()
        observed = marker.exists() and marker.read_bytes() == b"observed\n"
        tree_gone = state is not None and state.active == 0 and child.returncode is not None
        transport_ok = all_stopped and not transport_faults
        cancelled = stop_request.is_set()
        record = {
            "schema": SCHEMA, "client_stdin_eof": input_eof, "child_stdin_closed": stdin_closed_at is not None,
            "server_eof_observed": observed, "server_exit_code": child.returncode, "forced_termination": forced,
            "termination_reason": forced_reason or (
                "cancelled" if cancelled else next(iter(transport_faults), "child_exited")),
            "process_tree_verified_gone": tree_gone, "processes_in_owned_job": state.total if state is not None else None,
            "active_processes_at_check": state.active if state is not None else None,
            "pump_threads_started": len(pumps), "pump_threads_stopped": len(pumps) - len(outstanding),
            "pump_threads_verified_stopped": all_stopped, "outstanding_pump_threads": outstanding,
            "transport_ok": transport_ok, "transport_faults": list(transport_faults),
            "transport_fault_winerrors": {name: code for name, code in transport_faults.items() if code is not None},
            "stdin_bytes_forwarded": counts["input"], "stdout_bytes_forwarded": counts["output"],
            "stderr_bytes_seen": counts["stderr"], "stderr_bytes_retained": len(diagnostic),
            "stderr_truncated": counts["stderr"] > len(diagnostic), "elapsed_seconds": round(time.monotonic() - started, 6),
        }
        record["lifecycle_valid"] = (observed and input_eof and record["child_stdin_closed"] and child.returncode == 0
                                     and not forced and tree_gone and transport_ok and not cancelled)
        return record, bytes(diagnostic)

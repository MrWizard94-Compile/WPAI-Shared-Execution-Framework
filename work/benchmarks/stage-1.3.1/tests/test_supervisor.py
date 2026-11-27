from contextlib import ExitStack
import ctypes
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import winjob
from winjob import Job
from supervisor import Faults, Limits, Pump, forward, write_all
from wrapper import prepare


@unittest.skipUnless(os.name == "nt", "Windows Job Object tests")
class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory()))
        self.script = self.root / "worker.py"
        self.output = BytesIO()

    def open_pipe(self):
        read_fd, write_fd = os.pipe()
        return tuple(self.stack.enter_context(os.fdopen(fd, mode, buffering=0))
                     for fd, mode in ((read_fd, "rb"), (write_fd, "wb")))

    def exercise(self, code, incoming=None, outgoing=None, *, timeout=4, cancel=None, all_pumps_stop=True):
        self.script.write_text("import os, subprocess, sys, time\n" + code, encoding="utf-8")
        record, diagnostic = forward(
            BytesIO() if incoming is None else incoming,
            self.output if outgoing is None else outgoing,
            self.script, limits=Limits(timeout, 0.4, 2, 32), cancel=cancel)
        self.assertTrue(record["process_tree_verified_gone"], record)
        self.assertEqual(record["active_processes_at_check"], 0, record)
        self.assertEqual(record["pump_threads_started"], 3, record)
        if all_pumps_stop:
            self.assert_pumps_stopped(record)
        return record, diagnostic

    def assert_pumps_stopped(self, record):
        self.assertEqual(record["pump_threads_stopped"], 3, record)
        self.assertTrue(record["pump_threads_verified_stopped"], record)
        self.assertEqual(record["outstanding_pump_threads"], [], record)

    def assert_clean(self, record):
        self.assert_pumps_stopped(record)
        self.assertTrue(record["lifecycle_valid"], record)
        self.assertTrue(record["client_stdin_eof"])
        self.assertTrue(record["server_eof_observed"])
        self.assertEqual(record["server_exit_code"], 0)
        self.assertFalse(record["forced_termination"])

    def test_normal_client_shutdown(self):
        record, _ = self.exercise("while data := sys.stdin.buffer.read(17):\n os.write(1, data)\n", BytesIO(b"sample\n"))
        self.assert_clean(record)
        self.assertEqual(self.output.getvalue(), b"sample\n")

    def test_normal_server_shutdown_with_open_client_pipe(self):
        incoming, _ = self.open_pipe()
        record, _ = self.exercise("os.write(1, b'final\\n')\n", incoming)
        self.assertEqual(record["server_exit_code"], 0)
        self.assertFalse(record["server_eof_observed"])
        self.assertFalse(record["forced_termination"])
        self.assertTrue(record["transport_ok"], record)
        self.assertFalse(record["lifecycle_valid"])
        self.assertEqual(self.output.getvalue(), b"final\n")

    def test_client_closes_stdin_before_sending_a_request(self):
        record, _ = self.exercise("assert sys.stdin.buffer.read(1) == b''\n")
        self.assert_clean(record)
        self.assertEqual(record["stdin_bytes_forwarded"], 0)

    def test_client_exits_before_reply(self):
        incoming, writer = self.open_pipe()
        reader, outgoing = self.open_pipe()
        with subprocess.Popen([sys.executable, "-I", "-S", "-B", "-c",
                               "import os; os.write(1, b'request\\n')"],
                              stdin=reader, stdout=writer) as client:
            reader.close()
            writer.close()
            self.assertEqual(client.wait(timeout=4), 0)
        record, _ = self.exercise(
            "sys.stdin.buffer.readline(32)\nassert not sys.stdin.buffer.read(1)\nos.write(1, b'reply\\n')\n",
            incoming, outgoing)
        self.assertTrue(record["server_eof_observed"], record)
        self.assertIn("stdout_pipe_error", record["transport_faults"])
        self.assertFalse(record["lifecycle_valid"])

    def test_real_server_crash_and_bounded_stderr(self):
        record, diagnostic = self.exercise("os.write(2, b'x' * 20000)\nraise SystemExit(7)\n")
        self.assertEqual(record["server_exit_code"], 7)
        self.assertFalse(record["forced_termination"])
        self.assertEqual(self.output.getvalue(), b"")
        self.assertEqual(diagnostic, b"x" * 32)
        self.assertEqual(record["stderr_bytes_seen"], 20000)
        self.assertTrue(record["stderr_truncated"])

    def test_broken_stdout_pipe_while_client_stdin_remains_open(self):
        incoming, _ = self.open_pipe()
        reader, outgoing = self.open_pipe()
        reader.close()
        record, _ = self.exercise("os.write(1, b'reply')\nwhile sys.stdin.buffer.read(5): pass\n", incoming, outgoing)
        self.assertIn("stdout_pipe_error", record["transport_faults"])
        self.assertFalse(record["lifecycle_valid"])

    def test_partial_input_output_and_writes(self):
        class ShortRead(BytesIO):
            def read1(self, size):
                return super().read(min(size, 3))

        class ShortWrite(BytesIO):
            def write(self, data):
                return super().write(data[:2])

        incoming = b'{"jsonrpc":"2.0","id":5,"method":"tools/list"}\n'
        output = ShortWrite()
        record, _ = self.exercise("while data := sys.stdin.buffer.read(4):\n os.write(1, data)\n",
                                  ShortRead(incoming), output)
        self.assert_clean(record)
        self.assertEqual(output.getvalue(), incoming)
        with self.assertRaises(BrokenPipeError):
            write_all(type("Broken", (), {"write": lambda self, data: 0})(), b"request")

    def test_malformed_json_rpc_reaches_pinned_fixture(self):
        record_file = self.root / "lifecycle.json"
        request = b'{malformed json\n'
        argv = [sys.executable, "-B", "-W", "error", str(HERE / "wrapper.py"),
                "treatment", "--record", str(record_file)]
        with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              bufsize=0) as client:
            response = []
            reader = threading.Thread(target=lambda: response.append(client.stdout.readline()), daemon=True)
            reader.start()
            try:
                write_all(client.stdin, request)
                reader.join(5)
                self.assertFalse(reader.is_alive())
                self.assertEqual(json.loads(response[0])["error"]["code"], -32700)
                client.stdin.close()
                self.assertEqual(client.wait(timeout=5), 0)
                self.assertEqual(client.stderr.read(), b"")
            finally:
                if client.poll() is None:
                    client.kill()
                    client.wait(timeout=3)
                reader.join(3)
        record = json.loads(record_file.read_bytes())
        self.assert_clean(record)
        self.assertEqual(record["stdin_bytes_forwarded"], len(request))

    def test_worker_exception_returns_mcp_error_without_hanging(self):
        trial = self.root / "trial"
        fixture = prepare(trial, "treatment")
        launcher = fixture.with_name("failing_fixture.py")
        launcher.write_text(
            "import server\n"
            "install = server.install\n"
            "def fail(*_args):\n raise RuntimeError('synthetic worker fault')\n"
            "def setup(*args):\n install(*args)\n server.app.health = fail\n"
            "server.install = setup\n"
            "raise SystemExit(server.main())\n", encoding="utf-8")
        request = [
            {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
                "capabilities": {}, "clientInfo": {"name": "offline", "version": "1"}}},
            {"method": "notifications/initialized"},
            {"id": 2, "method": "tools/call", "params": {"name": "repo_health_v1",
                "arguments": {"project": "fictional-clockwork-museum"}}},
        ]
        incoming, writer = self.open_pipe()
        readback, outgoing = self.open_pipe()
        answers = []
        errors = []

        def client():
            try:
                for message in request:
                    payload = json.dumps({"jsonrpc": "2.0", **message}).encode() + b"\n"
                    write_all(writer, payload)
                    if "id" in message:
                        answers.append(json.loads(readback.readline()))
            except (OSError, ValueError) as exc:
                errors.append(exc)
            finally:
                writer.close()

        thread = threading.Thread(target=client, daemon=True)
        thread.start()
        try:
            record, _ = forward(incoming, outgoing, launcher, ("treatment", str(trial / "trace.private")),
                                limits=Limits(4, 0.4, 2))
        finally:
            outgoing.close()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(answers[-1]["result"]["isError"])
        self.assertEqual(answers[-1]["result"]["structuredContent"]["reason"], "acquisition_error")
        self.assert_clean(record)

    def test_timeout_with_open_input(self):
        incoming, _ = self.open_pipe()
        record, _ = self.exercise("time.sleep(60)\n", incoming, timeout=0.6)
        self.assertEqual(record["termination_reason"], "timeout")
        self.assertTrue(record["forced_termination"])
        self.assertFalse(record["server_eof_observed"])

    def test_cancellation_closes_input_and_is_not_a_clean_trial(self):
        incoming, _ = self.open_pipe()
        cancel = threading.Event()
        timer = threading.Timer(0.25, cancel.set)
        timer.start()
        try:
            record, _ = self.exercise("while sys.stdin.buffer.read(5): pass\n", incoming, cancel=cancel)
        finally:
            timer.cancel()
            timer.join()
        self.assertEqual(record["termination_reason"], "cancelled")
        self.assertTrue(record["server_eof_observed"])
        self.assertEqual(record["server_exit_code"], 0)
        self.assertFalse(record["forced_termination"])
        self.assertFalse(record["lifecycle_valid"])

    def test_real_timeout_reaps_descendants(self):
        incoming, _ = self.open_pipe()
        record, _ = self.exercise(
            "subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', 'import time; time.sleep(60)'])\n"
            "time.sleep(60)\n", incoming, timeout=1.5)
        self.assertGreaterEqual(record["processes_in_owned_job"], 2)
        self.assertEqual(record["termination_reason"], "timeout")
        self.assertTrue(record["forced_termination"])
        self.assertNotEqual(record["server_exit_code"], 0)

    def test_server_exits_but_descendant_remains(self):
        incoming, _ = self.open_pipe()
        record, _ = self.exercise(
            "subprocess.Popen([sys.executable, '-I', '-S', '-B', '-c', 'import time; time.sleep(60)'])\n",
            incoming)
        self.assertEqual(record["server_exit_code"], 0)
        self.assertGreaterEqual(record["processes_in_owned_job"], 2)
        self.assertEqual(record["termination_reason"], "descendants_after_exit")
        self.assertTrue(record["forced_termination"])

    def test_unread_stdout_pipe_is_bounded(self):
        _, outgoing = self.open_pipe()
        record, _ = self.exercise("os.write(1, b'x' * 1000000)\n", outgoing=outgoing, timeout=1)
        self.assertFalse(record["transport_ok"])
        self.assertIn("stdout_drain_timeout", record["transport_faults"])
        self.assertTrue(record["forced_termination"])
        self.assertFalse(record["lifecycle_valid"])
        self.assert_pumps_stopped(record)

    def test_blocked_write_to_server_is_released_by_tree_cleanup(self):
        pending = b"x" * 1_000_000
        record, _ = self.exercise("time.sleep(60)\n", incoming=BytesIO(pending), timeout=1)
        self.assertLess(record["stdin_bytes_forwarded"], len(pending))
        self.assertTrue(record["forced_termination"])
        self.assertEqual(record["termination_reason"], "timeout")
        self.assertFalse(record["lifecycle_valid"])

    def test_disconnect_during_output_write_is_a_visible_pipe_failure(self):
        reader, outgoing = self.open_pipe()
        entered = threading.Event()
        observed_pending = threading.Event()
        writer_thread = []
        errors = []
        real_write = winjob.write_pipe
        query_pending = winjob.bind("GetThreadIOPendingFlag", winjob.w.BOOL, winjob.w.HANDLE,
                                    ctypes.POINTER(winjob.w.BOOL))

        def write(stream, data):
            if stream is outgoing and not writer_thread:
                writer_thread.append(threading.get_native_id())
                entered.set()
            return real_write(stream, data)

        def close_peer():
            try:
                if not entered.wait(3):
                    return
                handle = winjob.checked(winjob.open_thread(0x0040, False, writer_thread[0]))
                try:
                    pending = winjob.w.BOOL()
                    deadline = time.monotonic() + 2
                    while not pending.value and time.monotonic() < deadline:
                        winjob.checked(query_pending(handle, ctypes.byref(pending)))
                        if not pending.value:
                            time.sleep(0.005)
                    if pending.value:
                        observed_pending.set()
                finally:
                    winjob.checked(winjob.close_handle(handle))
            except OSError as error:
                errors.append(error.winerror)
            finally:
                reader.close()

        peer = threading.Thread(target=close_peer, daemon=True)
        peer.start()
        try:
            with patch.object(winjob, "write_pipe", side_effect=write):
                record, _ = self.exercise("os.write(1, b'x' * 1000000)\n", outgoing=outgoing)
            self.assertEqual(errors, [])
            self.assertTrue(observed_pending.is_set())
            self.assertIn("stdout_pipe_error", record["transport_faults"])
            self.assertFalse(record["transport_ok"])
        finally:
            peer.join(4)

    def test_unresponsive_pump_is_named_and_lifecycle_fails(self):
        entered, release, returned = (threading.Event() for _ in range(3))
        active_threads = []

        class Unresponsive(BytesIO):
            def write(self, data):
                active_threads.append(threading.current_thread())
                entered.set()
                try:
                    if not release.wait(8):
                        raise RuntimeError("test failed to release the synthetic stream")
                    return super().write(data)
                finally:
                    returned.set()

        try:
            started = time.monotonic()
            record, _ = self.exercise("os.write(1, b'reply')\n", outgoing=Unresponsive(), all_pumps_stop=False)
            self.assertTrue(entered.is_set())
            self.assertLess(time.monotonic() - started, 6)
            self.assertFalse(returned.is_set())
            self.assertEqual(record["pump_threads_stopped"], 2)
            self.assertFalse(record["pump_threads_verified_stopped"])
            self.assertEqual(record["outstanding_pump_threads"], ["stdout"])
            self.assertIn("stdout_thread_still_alive", record["transport_faults"])
            self.assertTrue(record["process_tree_verified_gone"])
            self.assertFalse(record["transport_ok"])
            self.assertFalse(record["lifecycle_valid"])
        finally:
            release.set()
            if entered.is_set():
                self.assertTrue(returned.wait(2))
                active_threads[0].join(2)
                self.assertFalse(active_threads[0].is_alive())

    def test_outer_owner_can_kill_the_in_band_wrapper_before_it_reports_eof(self):
        record_file = self.root / "record.json"
        code = (
            "import os, runpy, sys\n"
            "assert os.read(sys.stdin.fileno(), 1) == b'X'\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "sys.argv = sys.argv[2:]\n"
            "runpy.run_path(sys.argv[0], run_name='__main__')\n"
        )
        environment = dict(os.environ, TEMP=str(self.root), TMP=str(self.root))
        with Job() as owner, subprocess.Popen(
            [sys.executable, "-I", "-S", "-B", "-W", "error", "-c", code, str(HERE), str(HERE / "wrapper.py"),
             "treatment", "--record", str(record_file)],
            env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            bufsize=0,
        ) as wrapper:
            try:
                owner.assign(wrapper.pid)
                write_all(wrapper.stdin, b"X")
                deadline = time.monotonic() + 5
                while owner.accounting().active < 2 and wrapper.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertGreaterEqual(owner.accounting().active, 2)
                owner.terminate()
                self.assertNotEqual(wrapper.wait(timeout=3), 0)
                deadline = time.monotonic() + 3
                while owner.accounting().active and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(owner.accounting().active, 0)
            finally:
                if wrapper.poll() is None:
                    owner.terminate()
                    if wrapper.poll() is None:
                        wrapper.kill()
                    wrapper.wait(timeout=3)
        self.assertFalse(record_file.exists())


class Cancellation(unittest.TestCase):
    def fake_error(self, code):
        def cancel(_handle):
            ctypes.set_last_error(code)
            return 0
        return cancel

    def parked_pump(self, action=None, close_stream=lambda: None):
        release, entered = threading.Event(), threading.Event()

        def io(stop):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test did not release the pump")
            if action is not None:
                action(stop)

        faults = Faults()
        pump = Pump(io, "stdin", faults, close_stream)

        def cleanup():
            release.set()
            pump.thread.join(3)
            self.assertFalse(pump.thread.is_alive())

        self.addCleanup(cleanup)
        self.assertTrue(entered.wait(2))
        return pump, faults, release

    def test_success_is_a_request_and_not_an_io_completion(self):
        pump, faults, _ = self.parked_pump()
        with patch.object(winjob, "cancel_io", return_value=1) as request:
            pump.interrupt()
        request.assert_called_once()
        self.assertTrue(pump.stop.is_set())
        self.assertTrue(pump.thread.is_alive())
        self.assertEqual(faults.snapshot(), {})

    def test_no_pending_io_is_benign_and_stop_remains_set(self):
        pump, faults, _ = self.parked_pump()
        with patch.object(winjob, "cancel_io", side_effect=self.fake_error(winjob.ERROR_NOT_FOUND)) as request:
            pump.interrupt()
        request.assert_called_once()
        self.assertTrue(pump.stop.is_set())
        self.assertEqual(faults.snapshot(), {})

    def test_pump_io_exits_after_liveness_check_with_thread_handle_still_owned(self):
        closing = threading.Event()
        pump, faults, release = self.parked_pump(close_stream=closing.set)

        def cancel(handle):
            release.set()
            self.assertTrue(closing.wait(2))
            # The action has returned. The thread handle is still owned while
            # the pump finalizer waits for this in-flight cancellation call.
            self.assertTrue(pump.thread.is_alive())
            return self.fake_error(winjob.ERROR_NOT_FOUND)(handle)

        with patch.object(winjob, "cancel_io", side_effect=cancel) as request:
            pump.interrupt()
            pump.thread.join(2)
            self.assertFalse(pump.thread.is_alive())
            pump.interrupt()
        request.assert_called_once()
        self.assertEqual(faults.snapshot(), {})

    def test_target_thread_exits_between_liveness_check_and_native_cancel(self):
        release = threading.Event()
        target = threading.Thread(target=release.wait, args=(3,))
        target.start()
        handle = None
        try:
            handle = winjob.checked(winjob.open_thread(winjob.THREAD_TERMINATE, False, target.native_id))
            self.assertTrue(target.is_alive())

            def cancel(handle):
                release.set()
                target.join(2)
                self.assertFalse(target.is_alive())
                return self.fake_error(winjob.ERROR_NOT_FOUND)(handle)

            with patch.object(winjob, "cancel_io", side_effect=cancel) as request:
                self.assertFalse(winjob.cancel_pending_io(handle))
            request.assert_called_once_with(handle)
        finally:
            release.set()
            target.join(2)
            if handle is not None:
                winjob.checked(winjob.close_handle(handle))

    def test_repeated_interrupt_after_stop_is_idempotent(self):
        pump, faults, release = self.parked_pump()
        with patch.object(winjob, "cancel_io", side_effect=self.fake_error(winjob.ERROR_NOT_FOUND)) as request:
            for _ in range(4):
                pump.interrupt()
                self.assertTrue(pump.stop.is_set())
            release.set()
            pump.thread.join(2)
            pump.interrupt()
        self.assertEqual(request.call_count, 4)
        self.assertEqual(faults.snapshot(), {})

    def test_other_windows_cancel_failure_is_retained_once(self):
        pump, faults, _ = self.parked_pump()
        with patch.object(winjob, "cancel_io", side_effect=self.fake_error(5)) as request:
            pump.interrupt()
            pump.interrupt()
        self.assertEqual(request.call_count, 2)
        self.assertTrue(pump.stop.is_set())
        self.assertEqual(faults.snapshot(), {"stdin_cancel_error": 5})

    def test_io_can_complete_normally_while_api_reports_success(self):
        finished = threading.Event()
        pump, faults, release = self.parked_pump(action=lambda _stop: finished.set())

        def cancel(_handle):
            release.set()
            self.assertTrue(finished.wait(2))
            return 1

        with patch.object(winjob, "cancel_io", side_effect=cancel):
            pump.interrupt()
        pump.thread.join(2)
        self.assertFalse(pump.thread.is_alive())
        self.assertEqual(faults.snapshot(), {})

    def test_only_the_expected_aborted_io_error_is_benign_after_stop(self):
        for code, expected in ((winjob.ERROR_OPERATION_ABORTED, {}), (5, {"stdin_pipe_error": 5})):
            with self.subTest(code=code):
                def action(_stop):
                    raise ctypes.WinError(code)
                pump, faults, release = self.parked_pump(action=action)
                pump.interrupt()
                release.set()
                pump.thread.join(2)
                self.assertFalse(pump.thread.is_alive())
                self.assertEqual(faults.snapshot(), expected)

    def test_injected_cancel_failure_reaches_supervisor_record_after_cleanup(self):
        with TemporaryDirectory() as directory:
            script = Path(directory) / "worker.py"
            ready = Path(directory) / "started"
            script.write_text(
                "from pathlib import Path\nimport sys, time\n"
                "deadline = time.monotonic() + 3\n"
                "while not Path(sys.argv[1]).exists() and time.monotonic() < deadline:\n time.sleep(0.005)\n",
                encoding="utf-8")
            entered, release = threading.Event(), threading.Event()

            class DelayedEof(BytesIO):
                def read1(self, _size):
                    entered.set()
                    ready.touch()
                    if not release.wait(4):
                        raise RuntimeError("test did not release input")
                    return b""

            def cancel(handle):
                self.assertTrue(entered.wait(2))
                release.set()
                return self.fake_error(5)(handle)

            with patch.object(winjob, "cancel_io", side_effect=cancel):
                record, _ = forward(DelayedEof(), BytesIO(), script, (str(ready),), limits=Limits(4, 0.5, 2))
            self.assertIn("stdin_cancel_error", record["transport_faults"])
            self.assertEqual(record["transport_fault_winerrors"]["stdin_cancel_error"], 5)
            self.assertTrue(record["pump_threads_verified_stopped"])
            self.assertTrue(record["process_tree_verified_gone"])
            self.assertFalse(record["transport_ok"])
            self.assertFalse(record["lifecycle_valid"])


if __name__ == "__main__":
    unittest.main()

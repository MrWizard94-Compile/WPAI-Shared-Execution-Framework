from contextlib import ExitStack
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


HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from winjob import Job
from supervisor import Limits, forward, write_all
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

    def exercise(self, code, incoming=None, outgoing=None, *, timeout=4, cancel=None):
        self.script.write_text("import os, subprocess, sys, time\n" + code, encoding="utf-8")
        record, diagnostic = forward(
            BytesIO() if incoming is None else incoming,
            self.output if outgoing is None else outgoing,
            self.script, limits=Limits(timeout, 0.4, 2, 32), cancel=cancel)
        self.assertTrue(record["process_tree_verified_gone"], record)
        self.assertEqual(record["active_processes_at_check"], 0, record)
        return record, diagnostic

    def assert_clean(self, record):
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


if __name__ == "__main__":
    unittest.main()

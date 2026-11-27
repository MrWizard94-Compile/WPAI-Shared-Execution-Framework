import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

import repo_health
import wpai_exec as app


CLIENT = {"name": "synthetic-client", "version": "1"}
OK = {"contract": "wpai.repo_health.v1", "status": "OK", "facts": {}}


class Incoming:
    def __init__(self):
        self.lines = Queue()
        self.remaining = b""

    def readline(self, limit):
        if not self.remaining:
            self.remaining = self.lines.get()
        piece, self.remaining = self.remaining[:limit], self.remaining[limit:]
        return piece


class Outgoing:
    def __init__(self):
        self.lines = Queue()

    def write(self, data):
        self.lines.put(bytes(data))
        return len(data)

    def flush(self):
        pass


class Session:
    def __init__(self, test, outgoing=None):
        self.test = test
        self.incoming = Incoming()
        self.outgoing = outgoing if outgoing is not None else Outgoing()
        self.server = app.Stdio(self.incoming, self.outgoing)
        self.exit_codes = []
        self.thread = threading.Thread(target=lambda: self.exit_codes.append(self.server.serve()), daemon=True)
        self.thread.start()
        self.test.addCleanup(self.close)

    def send(self, method, request_id=None, **params):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            msg["id"] = request_id
        self.raw(json.dumps(msg).encode() + b"\n")

    def raw(self, data):
        self.incoming.lines.put(data)

    def reply(self):
        return json.loads(self.outgoing.lines.get(timeout=3))

    def close(self):
        self.raw(b"")
        self.thread.join(3)
        self.test.assertEqual(self.exit_codes, [0])
        self.test.assertIsNone(self.server.active)
        if self.server.worker:
            self.test.assertFalse(self.server.worker.is_alive())


def metadata(version=app.MODERN, **overrides):
    return {"_meta": {app.META + "protocolVersion": version, app.META + "clientCapabilities": {}, **overrides}}


def open_protocol(session, version):
    if version == app.MODERN:
        session.send("server/discover", "open", **metadata())
        return session.reply()
    session.send("initialize", "open", protocolVersion=version, capabilities={}, clientInfo=CLIENT)
    reply = session.reply()
    session.send("notifications/initialized")
    return reply


# Required top-level fields projected from each revision's normative schema at
# modelcontextprotocol/modelcontextprotocol@024d5255eb4466ba4fab21e044b5ba84d6a79327.
# Constants and type constraints relevant to this one-operation subset follow below.
WIRE_RESULTS = {
    "2025-06-18": {"open": {"capabilities", "protocolVersion", "serverInfo"},
                   "list": {"tools"}, "call": {"content"}},
    "2025-11-25": {"open": {"capabilities", "protocolVersion", "serverInfo"},
                   "list": {"tools"}, "call": {"content"}},
    "2026-07-28": {"open": {"cacheScope", "capabilities", "resultType", "supportedVersions", "ttlMs"},
                   "list": {"cacheScope", "resultType", "tools", "ttlMs"},
                   "call": {"content", "resultType"}},
}


class ProtocolTests(unittest.TestCase):
    def wire(self, response, request_id, version, kind):
        self.assertEqual(set(response), {"jsonrpc", "id", "result"})
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], request_id)
        result = response["result"]
        self.assertIsInstance(result, dict)
        self.assertTrue(WIRE_RESULTS[version][kind] <= result.keys())
        if version == app.MODERN:
            self.assertEqual(result["resultType"], "complete")
            self.assertEqual(result["_meta"][app.META + "serverInfo"], app.INFO)
            self.assertNotIn("serverInfo", result)
            if kind in ("open", "list"):
                self.assertEqual((result["ttlMs"], result["cacheScope"]), (0, "private"))
        else:
            self.assertNotIn("resultType", result)
            self.assertNotIn("_meta", result)
            if kind == "open":
                self.assertEqual(result["protocolVersion"], version)
                self.assertEqual(result["serverInfo"], app.INFO)
        if kind == "open":
            self.assertEqual(result["capabilities"], {"tools": {"listChanged": False}})
        if kind == "call":
            content = result["content"]
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0]["type"], "text")
            self.assertIsInstance(content[0]["text"], str)
            self.assertIs(type(result["isError"]), bool)
            self.assertEqual(json.loads(content[0]["text"]), result["structuredContent"])
        return result

    def test_all_revisions_discover_same_catalog_and_preserve_tool_semantics(self):
        for version in WIRE_RESULTS:
            with self.subTest(version=version):
                session = Session(self)
                envelope = metadata() if version == app.MODERN else {}
                hello = self.wire(open_protocol(session, version), "open", version, "open")
                if version == app.MODERN:
                    self.assertEqual(hello["supportedVersions"], list(app.SUPPORTED))
                for request_id in (1, 2):
                    session.send("tools/list", request_id, **envelope)
                    catalog = self.wire(session.reply(), request_id, version, "list")["tools"]
                    self.assertEqual(catalog, [app.TOOL_SPEC])
                    self.assertEqual(catalog[0]["inputSchema"]["type"], "object")
                    self.assertEqual(catalog[0]["outputSchema"]["properties"]["contract"]["const"], app.CONTRACT)
                for request_id, arguments, status in (
                    (3, {"project": "trackforge"}, "OK"), (4, {"project": "other"}, "DENIED"),
                    (5, {"project": "trackforge", "path": "ignored"}, "INVALID_ARGUMENTS"),
                ):
                    with patch("repo_health.Reader") as reader:
                        def collect(args, cancellation):
                            return OK if args == {"project": "trackforge"} else repo_health.health(args, cancellation)

                        with patch.object(app, "health", side_effect=collect):
                            session.send("tools/call", request_id, name=app.TOOL, arguments=arguments, **envelope)
                            result = self.wire(session.reply(), request_id, version, "call")
                        reader.assert_not_called()
                    self.assertEqual(result["structuredContent"]["status"], status)
                    self.assertEqual(result["isError"], status != "OK")
                    self.assertIsNone(session.server.active)
                session.close()
                self.assertFalse(session.server.writer.is_alive())

    def test_legacy_fallback_requires_initialization_and_allows_handshake_ping(self):
        session = Session(self)
        session.send("tools/list", 1)
        self.assertEqual(session.reply()["error"]["code"], -32002)
        session.send("initialize", 2, protocolVersion="1900-01-01", capabilities={})
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("initialize", 3, protocolVersion="1900-01-01", capabilities={}, clientInfo=CLIENT)
        self.wire(session.reply(), 3, "2025-11-25", "open")
        session.send("ping", 4)
        self.assertEqual(session.reply()["result"], {})
        session.send("tools/list", 5)
        self.assertEqual(session.reply()["error"]["code"], -32002)
        session.send("notifications/initialized")
        session.send("tools/list", 6, cursor=None)
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("tools/list", 7)
        self.wire(session.reply(), 7, "2025-11-25", "list")

    def test_modern_request_metadata_errors_and_framing_recovery(self):
        session = Session(self)
        session.raw(b" " * (app.MAX_LINE * 2) + b"\n")
        self.assertEqual(session.reply()["error"]["code"], -32600)
        session.send("server/discover", 1, **metadata("1900-01-01"))
        error = session.reply()
        self.assertEqual(error["id"], 1)
        self.assertEqual(error["error"], {"code": -32022, "message": "Unsupported protocol version",
                                          "data": {"requested": "1900-01-01", "supported": list(app.SUPPORTED)}})
        session.send("server/discover", 2)
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("tools/list", 3, _meta={app.META + "protocolVersion": app.MODERN})
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("tools/list", 4, **metadata(**{app.META + "clientInfo": {"name": "incomplete"}}))
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.raw(b'{"jsonrpc":"2.0","jsonrpc":"2.0","id":5,"method":"tools/list"}\n')
        self.assertEqual(session.reply(), {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Invalid JSON"}})
        session.send("tools/list", 6)
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("ping", 7, **metadata())
        self.assertEqual(session.reply()["error"]["code"], -32601)
        session.send("tools/call", 8, name="unknown", **metadata())
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("tools/call", 9, name=app.TOOL, arguments=[], **metadata())
        self.assertEqual(session.reply()["error"]["code"], -32602)
        session.send("tools/list", 10, **metadata(**{app.META + "clientInfo": CLIENT}))
        self.wire(session.reply(), 10, app.MODERN, "list")


class LifecycleTests(unittest.TestCase):
    def call_tool(self, session, request_id, envelope=None):
        session.send("tools/call", request_id, name=app.TOOL, arguments={"project": "trackforge"},
                     **(metadata() if envelope is None else envelope))

    def test_recoverable_exception_has_generic_reply_and_releases_active_slot(self):
        session = Session(self)
        private_message = r"private-marker C:\secret\provider-token"
        with patch.object(app, "result", side_effect=[KeyError(private_message), (OK, app.compact(OK))]):
            self.call_tool(session, 1)
            error = session.reply()
            self.assertNotIn("private-marker", repr(error))
            self.assertEqual(error["result"]["structuredContent"], {
                "contract": app.CONTRACT, "status": "UNAVAILABLE", "reason": "acquisition_error"})
            self.assertIsNone(session.server.active)
            self.call_tool(session, 2)
            self.assertEqual(session.reply()["result"]["structuredContent"], OK)
        self.assertIsNone(session.server.active)

    def test_encoding_failure_returns_generic_rpc_error_and_releases_active_slot(self):
        session = Session(self)
        with patch.object(app, "result", return_value=({"status": "OK", "invalid": {"private-marker"}}, "{}")):
            self.call_tool(session, 1)
            self.assertEqual(session.reply(), {"jsonrpc": "2.0", "id": 1,
                                               "error": {"code": -32603, "message": "Could not encode repository result"}})
        self.assertIsNone(session.server.active)

    def test_concurrency_and_cancellation_in_all_revisions(self):
        for version in WIRE_RESULTS:
            with self.subTest(version=version):
                session = Session(self)
                open_protocol(session, version)
                envelope = metadata() if version == app.MODERN else {}
                entered, stopped = threading.Event(), threading.Event()

                def collect(_arguments, cancellation):
                    entered.set()
                    if cancellation.wait(2):
                        stopped.set()
                    return OK

                with patch.object(app, "health", side_effect=collect) as mock:
                    self.call_tool(session, 3, envelope)
                    self.assertTrue(entered.wait(1))
                    session.send("notifications/cancelled", requestId="different")
                    self.call_tool(session, 4, envelope)
                    self.assertEqual(session.reply()["error"]["code"], -32000)
                    self.assertEqual(mock.call_count, 1)
                    session.send("notifications/cancelled", requestId=3)
                    self.assertTrue(stopped.wait(1))
                    session.server.worker.join(1)
                    self.assertFalse(session.server.worker.is_alive())
                    self.assertIsNone(session.server.active)
                    session.send("tools/list", 5, **envelope)
                    self.assertEqual(session.reply()["id"], 5)
                session.close()
                self.assertTrue(session.outgoing.lines.empty())

    def test_eof_cancels_active_worker_and_suppresses_reply(self):
        session = Session(self)
        started, cancelled = threading.Event(), threading.Event()

        def collect(_arguments, cancellation):
            started.set()
            if cancellation.wait(2):
                cancelled.set()
            return OK

        with patch.object(app, "health", side_effect=collect):
            self.call_tool(session, 1)
            self.assertTrue(started.wait(1))
            session.close()
        self.assertTrue(cancelled.is_set())
        self.assertTrue(session.outgoing.lines.empty())
        self.assertFalse(session.server.writer.is_alive())

    def test_send_failure_closes_transport_without_stranding_acquisition(self):
        attempted = threading.Event()

        class BrokenOutput(Outgoing):
            def write(self, data):
                attempted.set()
                raise BrokenPipeError("private-marker")

        session = Session(self, BrokenOutput())
        with patch.object(app, "health", return_value=OK):
            self.call_tool(session, 1)
            self.assertTrue(attempted.wait(1))
            session.server.writer.join(1)
            self.assertTrue(session.server.closed)
            session.thread.join(1)
            self.assertFalse(session.thread.is_alive())
            session.close()
        self.assertTrue(session.outgoing.lines.empty())

    def test_stdout_backpressure_does_not_hold_acquisition_or_eof(self):
        entered, release = threading.Event(), threading.Event()

        class BlockedOutput(Outgoing):
            def write(self, data):
                entered.set()
                release.wait(4)
                raise BrokenPipeError

        session = Session(self, BlockedOutput())
        try:
            with patch.object(app, "health", return_value=OK):
                self.call_tool(session, 1)
                self.assertTrue(entered.wait(1))
                self.assertIsNone(session.server.active)
                session.close()
        finally:
            release.set()
            session.server.writer.join(1)
        self.assertFalse(session.server.writer.is_alive())

    def test_cancellation_drops_a_result_queued_behind_another_reply(self):
        entered, release, collected = threading.Event(), threading.Event(), threading.Event()

        class HeldOutput(Outgoing):
            def write(self, data):
                if not entered.is_set():
                    entered.set()
                    release.wait(4)
                return super().write(data)

        def collect(_args, _cancellation):
            collected.set()
            return OK

        session = Session(self, HeldOutput())
        session.send("tools/list", 1, **metadata())
        try:
            self.assertTrue(entered.wait(1))
            with patch.object(app, "health", side_effect=collect):
                self.call_tool(session, 2)
                self.assertTrue(collected.wait(1))
                with session.server.lock:
                    worker = session.server.worker
                worker.join(1)
                cancellation = session.server.queued_calls[2]
                session.send("notifications/cancelled", requestId=2)
                self.assertTrue(cancellation.wait(1))
                session.send("tools/list", 3, **metadata())
        finally:
            release.set()
        self.assertEqual(session.reply()["id"], 1)
        self.assertEqual(session.reply()["id"], 3)

    def test_process_exits_on_stdin_eof_even_if_peer_never_reads_stdout(self):
        script = """
import sys
import wpai_exec as app

class SignalledOutput:
    def write(self, data):
        print('writing', file=sys.stderr, flush=True)
        return sys.stdout.buffer.raw.write(data)

    def flush(self):
        pass

app.health = lambda _args, _cancel: {'contract': app.CONTRACT, 'status': 'OK', 'facts': {'synthetic': 'z' * 90000}}
sys.exit(app.Stdio(sys.stdin.buffer.raw, SignalledOutput()).serve())
"""
        frame = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                 "params": {"name": app.TOOL, "arguments": {"project": "trackforge"}, **metadata()}}
        process = subprocess.Popen([sys.executable, "-B", "-W", "error", "-c", script],
                                   cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        marker = Queue()
        reader = threading.Thread(target=lambda: marker.put(process.stderr.readline()), daemon=True)
        reader.start()
        try:
            process.stdin.write(json.dumps(frame).encode() + b"\n")
            process.stdin.flush()
            self.assertEqual(marker.get(timeout=4).strip(), b"writing")
            process.stdin.close()
            self.assertEqual(process.wait(timeout=4), 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=4)
            reader.join(1)
            process.stdin.close()
            process.stdout.close()
            process.stderr.close()

    def test_real_process_exits_on_broken_stdout_while_stdin_remains_open(self):
        root = Path(__file__).resolve().parents[1]
        process = subprocess.Popen([sys.executable, "-B", "-W", "error", "wpai_exec.py", "stdio"], cwd=root,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        frame = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": metadata()}
        try:
            process.stdout.close()
            process.stdin.write(json.dumps(frame).encode() + b"\n")
            process.stdin.flush()
            self.assertEqual(process.wait(timeout=4), 0)
            self.assertEqual(process.stderr.read(), b"")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=4)
            process.stdin.close()
            process.stderr.close()


if __name__ == "__main__":
    unittest.main()

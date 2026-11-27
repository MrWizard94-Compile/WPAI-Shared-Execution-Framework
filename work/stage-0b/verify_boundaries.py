"""Negative frame and process checks for the synthetic MCP probe."""

import json
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent
CALL = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "probe_denied_operation", "arguments": {"unexpected": True}}}
META = {"io.modelcontextprotocol/protocolVersion": "1900-01-01",
        "io.modelcontextprotocol/clientCapabilities": {}}


def frame(payload):
    return json.dumps(payload).encode("utf-8") + b"\n"


def run(data):
    return subprocess.run(
        [sys.executable, "-I", "-B", str(BASE / "probe.py")],
        cwd=BASE, input=data, capture_output=True, timeout=5, check=False,
    )


def main():
    result = run(
        frame(CALL) +
        b'{"jsonrpc":"2.0","id":2,"id":3,"method":"ping"}\n' +
        frame({"jsonrpc": "2.0", "id": 4, "method": "server/discover", "params": {"_meta": META}}) +
        frame({"jsonrpc": "2.0", "id": 5, "method": "initialize",
               "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                          "clientInfo": {"name": "boundary-check", "version": "1"}}}) +
        frame({"jsonrpc": "2.0", "method": "notifications/initialized"}) +
        frame({**CALL, "id": 6})
    )
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert result.returncode == 0 and len(replies) == 5
    assert [entry.get("error", {}).get("code") for entry in replies[:3]] == [-32002, -32700, -32022]
    returned = replies[-1]["result"]
    assert returned["isError"] is True
    assert json.loads(returned["content"][0]["text"]) == {"code": "DENIED", "protectedActions": 0}
    reported = [json.loads(line) for line in result.stderr.splitlines()]
    assert sum(event.get("outcome") == "DENIED" for event in reported) == 1
    oversized = run(b"x" * 8192 + b"\n")
    assert oversized.returncode == 2 and not oversized.stdout
    assert json.loads(oversized.stderr.splitlines()[-1])["reason"] == "frame_limit"
    ceiling = run(frame({"jsonrpc": "2.0", "method": "noop"}) * 129)
    assert ceiling.returncode == 2 and not ceiling.stdout
    assert json.loads(ceiling.stderr.splitlines()[-1])["reason"] == "message_limit"
    print(json.dumps({
        "checks": ["uninitialized_call_rejected", "duplicate_json_key_rejected",
                   "unsupported_protocol_rejected", "authorization_before_argument_dispatch",
                   "frame_limit", "message_limit", "stdio_json_only", "exit_on_eof"],
        "protectedActions": 0,
    }))


if __name__ == "__main__":
    main()

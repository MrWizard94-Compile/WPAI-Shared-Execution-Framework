"""Run the synthetic fixture through native client entry points without signing in."""

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from queue import Queue, Empty
from tempfile import mkdtemp
from threading import Thread
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from probe import CURSOR_TTL

BASE = Path(__file__).resolve().parent
LABEL = "wpai_probe"
LEGACY = "2025-06-18"
MODERN = "2026-07-28"
TOOLS = {
    "probe_info", "probe_echo", "probe_validation",
    "probe_evidence_page", "probe_denied_operation",
}
ECHO = {"value": {"label": "WPAI", "count": 7, "enabled": True}}


def as_json(file, data):
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def trace_events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def command_path(name):
    full_path = shutil.which(name)
    if full_path is None:
        raise RuntimeError(f"Cannot resolve {name}")
    return full_path


def isolated_env(case):
    home = case / "home"
    for folder in [home, home / "roaming", home / "local", case / "tmp"]:
        folder.mkdir(parents=True, exist_ok=True)
    keys = (
        "SystemRoot", "WINDIR", "ComSpec", "Path", "PATHEXT", "ProgramFiles",
        "ProgramFiles(x86)", "ProgramData", "PROCESSOR_ARCHITECTURE", "SystemDrive",
    )
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env.update(
        HOME=str(home), USERPROFILE=str(home),
        APPDATA=str(home / "roaming"), LOCALAPPDATA=str(home / "local"),
        TEMP=str(case / "tmp"), TMP=str(case / "tmp"),
        CODEX_HOME=str(home / ".codex"), GROK_HOME=str(home / ".grok"),
        CLAUDE_CONFIG_DIR=str(home / ".claude"), GEMINI_CLI_HOME=str(home),
        DISABLE_AUTOUPDATER="1", DISABLE_TELEMETRY="1",
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
        GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
        HTTP_PROXY="http://127.0.0.1:1", HTTPS_PROXY="http://127.0.0.1:1",
        ALL_PROXY="http://127.0.0.1:1", NO_PROXY="",
        GOOGLE_APPLICATION_CREDENTIALS=str(case / "nonexistent-credentials.json"),
    )
    return env


def client_command(argv, cwd, env, timeout=22):
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )
        return {"exit": result.returncode, "stdout": result.stdout[-5000:], "stderr": result.stderr[-2500:]}
    except subprocess.TimeoutExpired:
        return {"exit": None, "timeoutSeconds": timeout}


class RpcFailure(Exception):
    pass


class ProcessRpc:
    def __init__(self, argv, cwd, env, stderr):
        self.process = subprocess.Popen(
            argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            text=True, encoding="utf-8", errors="replace",
        )
        self.lines = Queue()
        self.counter = 0
        self.unrelated = 0
        Thread(target=self.pump, daemon=True).start()

    def pump(self):
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, frame):
        self.process.stdin.write(json.dumps(frame) + "\n")
        self.process.stdin.flush()

    def notify(self, method, params=None):
        frame = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            frame["params"] = params
        self.send(frame)

    def call(self, method, params, timeout=12):
        self.counter += 1
        request_id = self.counter
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = self.lines.get(timeout=max(0, deadline - time.monotonic()))
            except Empty as exc:
                raise RpcFailure(f"Timed out on {method}") from exc
            if line is None:
                raise RpcFailure(f"Process closed while awaiting {method}")
            try:
                frame = json.loads(line)
            except ValueError as exc:
                raise RpcFailure(f"Non-JSON stdout while awaiting {method}") from exc
            if frame.get("id") == request_id and ("result" in frame or "error" in frame):
                if "error" in frame:
                    raise RpcFailure(f"{method}: {frame['error']}")
                return frame["result"]
            self.unrelated += 1

    def close(self):
        self.process.stdin.close()
        try:
            return {"exit": self.process.wait(8), "forced": False}
        except subprocess.TimeoutExpired:
            self.process.terminate()
            return {"exit": self.process.wait(8), "forced": True}


@contextmanager
def rpc_process(argv, cwd, env, stderr, outcome):
    with stderr.open("w", encoding="utf-8") as errors:
        rpc = ProcessRpc(argv, cwd, env, errors)
        try:
            yield rpc
        finally:
            outcome["process"] = rpc.close()


def decode(result):
    text = next(block["text"] for block in result["content"] if block["type"] == "text")
    content = json.loads(text)
    structured = result.get("structuredContent")
    if not result.get("isError"):
        assert structured == content, f"Structured and text differ: {result}"
    return content


def operation_checks(call, protocol):
    checks = {}

    def expect(name, tool, args, expected, is_error=False):
        reply = call(tool, args)
        actual = decode(reply)
        assert bool(reply.get("isError", False)) == is_error, (name, reply)
        if isinstance(expected, dict):
            assert actual == expected, (name, actual)
        else:
            assert expected(actual), (name, actual)
        checks[name] = actual
        return actual

    expect("info", "probe_info", {}, lambda r: (
        r["protocol"] == protocol and r["contract"] == "wpai.probe.v1" and
        r["supported"] == [MODERN, "2025-11-25", LEGACY]
    ))
    expect("echo", "probe_echo", ECHO, ECHO)
    expect("valid", "probe_validation", {"count": 9}, {"valid": True, "count": 9})
    for name, args, reason in [
        ("invalidType", {"count": "9"}, "Expected an integer"),
        ("invalidBool", {"count": True}, "Expected an integer"),
        ("unexpectedProperty", {"count": 3, "extra": 1}, "Unexpected property"),
        ("invalidRange", {"count": 10}, "Integer out of range"),
    ]:
        expect(name, "probe_validation", args, {"code": "INVALID_INPUT", "reason": reason}, True)
    expect("denied", "probe_denied_operation", {}, {"code": "DENIED", "protectedActions": 0}, True)
    first = expect("firstPage", "probe_evidence_page", {}, lambda r: (
        r["page"] == 1 and r["rows"] == ["alder", "birch"] and isinstance(r["nextCursor"], str)
    ))
    cursor = first["nextCursor"]
    expect("nextPage", "probe_evidence_page", {"cursor": cursor},
           {"page": 2, "rows": ["cedar", "dogwood"], "nextCursor": None})
    time.sleep(CURSOR_TTL + 0.15)
    expect("expiredCursor", "probe_evidence_page", {"cursor": cursor},
           {"code": "CURSOR_EXPIRED_OR_UNKNOWN"}, True)
    return checks


def server_args(run, label):
    return ["-I", "-B", str(BASE / "launch_probe.py"), str(run), label]


def definition(run, label):
    return {"command": sys.executable, "args": server_args(run, label)}


def direct(run, case, env, outcome, protocol):
    meta = {
        "io.modelcontextprotocol/protocolVersion": protocol,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "wpai-independent-driver", "version": "1"},
    }
    params = {"_meta": meta} if protocol == MODERN else {}
    args = [sys.executable, *server_args(run, case.name)]
    for attempt in range(2):
        result = {"attempt": attempt + 1}
        outcome.setdefault("reconnections", []).append(result)
        with rpc_process(args, case, env, case / f"driver-{attempt}.log", result) as rpc:
            if protocol == MODERN:
                discovery = rpc.call("server/discover", params)
                assert discovery["resultType"] == "complete" and protocol in discovery["supportedVersions"]
            else:
                hello = rpc.call("initialize", {
                    "protocolVersion": protocol, "capabilities": {},
                    "clientInfo": {"name": "wpai-independent-driver", "version": "1"},
                })
                assert hello["protocolVersion"] == protocol
                rpc.notify("notifications/initialized")
            listed = rpc.call("tools/list", params)
            assert {tool["name"] for tool in listed["tools"]} == TOOLS
            result["catalog"] = sorted(TOOLS)
            if attempt == 0:
                result["operations"] = operation_checks(
                    lambda name, arguments: rpc.call("tools/call", {
                        **params, "name": name, "arguments": arguments,
                    }), protocol,
                )
        assert result["process"] == {"exit": 0, "forced": False}


def sdk_legacy(run, case, env, outcome):
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def check():
        entry = StdioServerParameters(
            command=sys.executable, args=server_args(run, case.name), env=env, cwd=case,
        )
        with (case / "sdk-stderr.log").open("w", encoding="utf-8") as errors:
            async with stdio_client(entry, errlog=errors) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    hello = await client.initialize()
                    response = await client.list_tools()
                    assert {item.name for item in response.tools} == TOOLS
                    reply = await client.call_tool("probe_echo", ECHO)
                    assert decode(reply.model_dump(by_alias=True)) == ECHO
                    outcome.update(protocol=hello.protocolVersion, catalog=sorted(TOOLS), echo=ECHO)

    async def bounded():
        with anyio.fail_after(15):
            await check()

    anyio.run(bounded)


def codex(run, case, env, outcome, modern):
    home = Path(env["CODEX_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    config = (
        'approval_policy = "never"\n'
        'sandbox_mode = "read-only"\n'
        '[mcp_servers.wpai_probe]\n'
        f'command = {json.dumps(sys.executable)}\n'
        f'args = {json.dumps(server_args(run, case.name))}\n'
        'startup_timeout_sec = 8\ntool_timeout_sec = 8\nrequired = true\n'
    )
    if modern:
        config += (
            '[mcp_servers.wpai_probe.env]\n'
            'CODEX_MCP_PROTOCOL_VERSION = "2026-07-28"\n'
            '[features]\nmcp_2026_07_28 = true\n'
        )
    (home / "config.toml").write_text(config, encoding="utf-8")
    argv = [command_path("codex.exe"), "app-server", "--listen", "stdio://"]
    with rpc_process(argv, case, env, case / "app-server.stderr.log", outcome) as rpc:
        rpc.call("initialize", {
            "clientInfo": {"name": "wpai-stage-0b", "title": "WPAI Stage 0B", "version": "1"},
            "capabilities": {"experimentalApi": True, "requestAttestation": False},
        })
        rpc.notify("initialized")
        inventory = rpc.call("mcpServerStatus/list", {})
        server = next(item for item in inventory["data"] if item["name"] == LABEL)
        assert set(server["tools"]) == TOOLS
        outcome["catalog"] = sorted(server["tools"])
        thread_id = rpc.call("thread/start", {"cwd": str(case), "ephemeral": True})["thread"]["id"]

        def call(name, arguments):
            return rpc.call("mcpServer/tool/call", {
                "threadId": thread_id, "server": LABEL, "tool": name, "arguments": arguments,
            })

        outcome["operations"] = operation_checks(call, MODERN if modern else LEGACY)
        outcome["inferenceRequested"] = False


def grok(run, case, env, outcome):
    command = command_path("grok.exe")
    home = Path(env["GROK_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    entry = definition(run, case.name)
    cfg = (
        '[cli]\nauto_update = false\n'
        '[mcp_servers.wpai_probe]\n'
        f'command = {json.dumps(entry["command"])}\n'
        f'args = {json.dumps(entry["args"])}\n'
    )
    (home / "config.toml").write_text(cfg, encoding="utf-8")
    endpoint = str(case / "local-leader.sock")
    outcome["list"] = client_command(
        [command, "mcp", "--leader-socket", endpoint, "list", "--json"], case, env,
    )
    outcome["doctor"] = client_command(
        [command, "mcp", "--leader-socket", endpoint, "doctor", LABEL, "--json"], case, env,
    )


def claude(run, case, env, outcome):
    if case.name == "claude-modern":
        env.update(MCP_SDK_GENERATION="v2", MCP_PROTOCOL_NEGOTIATION="auto")
    cmd = command_path("claude.exe")
    cwd = case / "project"
    cwd.mkdir()
    config = definition(run, case.name)
    as_json(cwd / ".mcp.json", {"mcpServers": {LABEL: {"type": "stdio", **config}}})
    outcome["projectBeforeApproval"] = client_command([cmd, "mcp", "list"], cwd, env)
    user = case / "user-scope"
    user.mkdir()
    outcome["registerUser"] = client_command(
        [cmd, "mcp", "add", "--scope", "user", LABEL, "--", config["command"], *config["args"]],
        user, env,
    )
    outcome["userHealth"] = client_command([cmd, "mcp", "list"], user, env)


def gemini(run, case, env, outcome):
    node = command_path("node.exe")
    cli = Path(os.environ["APPDATA"]) / "npm/node_modules/@google/gemini-cli/bundle/gemini.js"
    assert cli.is_file()
    argv = [node, str(cli), "mcp", "list"]
    config = {"mcpServers": {LABEL: {**definition(run, case.name), "trust": False, "timeout": 6000}}}
    as_json(case / ".gemini/settings.json", config)
    outcome["workspaceMcp"] = client_command(argv, case, env)
    # Use a separate disposable profile to compare Gemini's folder trust policy.
    config["security"] = {"folderTrust": {"enabled": True}}
    as_json(case / ".gemini/settings.json", config)
    as_json(Path(env["HOME"]) / ".gemini/settings.json", {"security": config["security"]})
    as_json(Path(env["HOME"]) / ".gemini/trustedFolders.json", {str(case): "TRUST_FOLDER"})
    outcome["workspaceMcpExplicitTrust"] = client_command(argv, case, env)


def agy(run, case, env, outcome):
    exe = Path(os.environ["LOCALAPPDATA"]) / "agy/bin/agy.exe"
    as_json(case / ".agents/mcp_config.json", {"mcpServers": {LABEL: definition(run, case.name)}})
    outcome["workspaceMcp"] = client_command([str(exe), "mcp", "list"], case, env)
    user_scope = case / "user-scope"
    user_scope.mkdir()
    entry = definition(run, case.name)
    outcome["registerUser"] = client_command(
        [str(exe), "mcp", "add", LABEL, "--", entry["command"], *entry["args"]], user_scope, env,
    )
    outcome["userMcp"] = client_command([str(exe), "mcp", "list"], user_scope, env)
    argv = [
        str(exe), "acp", "--stdio", "--disable-telemetry",
        "--app-data-dir", "acp-app",
        "--gemini-dir", "acp-gemini",
        "--cloud_code_endpoint", "http://127.0.0.1:1",
    ]
    # ACP initialize and session/new are metadata/session methods. No authenticate or prompt.
    with rpc_process(argv, case, env, case / "acp.stderr.log", outcome) as rpc:
        response = rpc.call("initialize", {
            "protocolVersion": 1, "clientCapabilities": {},
            "clientInfo": {"name": "wpai-stage-0b", "version": "1"},
        })
        outcome["acp"] = {"protocol": response.get("protocolVersion"),
                          "authMethodIds": [method["id"] for method in response.get("authMethods", [])]}
        try:
            created = rpc.call("session/new", {"cwd": str(case), "mcpServers": [{"name": LABEL, **entry, "env": []}]}, timeout=10)
            outcome["acp"]["isolatedSessionCreated"] = bool(created.get("sessionId"))
        except RpcFailure as exc:
            outcome["acp"]["sessionError"] = str(exc)


CASES = {
    "direct-legacy": lambda *args: direct(*args, LEGACY),
    "direct-modern": lambda *args: direct(*args, MODERN),
    "sdk-legacy": sdk_legacy,
    "codex-legacy": lambda *args: codex(*args, False),
    "codex-modern": lambda *args: codex(*args, True),
    "grok": grok, "claude": claude, "claude-modern": claude, "gemini": gemini, "agy": agy,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", choices=CASES, nargs="+")
    parsed = parser.parse_args()
    results = BASE / "runs"
    results.mkdir(exist_ok=True)
    run = Path(mkdtemp(prefix="stage-0b-", dir=results))
    print(f"record_directory={run}", flush=True)
    failed = False
    for name in parsed.cases:
        case = run / name
        case.mkdir()
        outcome = {
            "case": name, "serverSHA256": sha256((BASE / "probe.py").read_bytes()).hexdigest(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        started = time.monotonic()
        try:
            CASES[name](run, case, isolated_env(case), outcome)
        except (AssertionError, OSError, KeyError, RpcFailure, StopIteration, RuntimeError) as exc:
            outcome["error"] = str(exc) or type(exc).__name__
            failed = True
        outcome["seconds"] = round(time.monotonic() - started, 3)
        outcome["wire"] = trace_events(run / f"{name}.wire.jsonl")
        as_json(run / f"{name}.json", outcome)
        print(json.dumps(outcome, ensure_ascii=True), flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

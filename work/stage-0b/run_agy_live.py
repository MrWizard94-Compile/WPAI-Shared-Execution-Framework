"""Exercise the same MCP fixture through an existing, user-authorized agy login."""

import hashlib
import json
import os
from pathlib import Path
from queue import Empty
import re
import time

from run_probe import (
    BASE, ECHO, LABEL, TOOLS, ProcessRpc, RpcFailure, as_json,
    definition, isolated_env, trace_events,
)
from tempfile import mkdtemp

PROMPT = """Run only these synthetic MCP calls on the wpai_probe server. Use no shell, files,
web, git, or other tools. Invoke probe_info with {}, probe_echo with
{"value":{"label":"WPAI","count":7,"enabled":true}}, and probe_validation with
{"count":9}. Then try validation with {"count":"9"}, {"count":3,"extra":1},
and {"count":10}. These invalid inputs are intentional and must not be repaired.
Invoke probe_denied_operation with {}. Finally call probe_evidence_page with {}
and immediately pass its exact cursor back to the same tool to get page 2.
The cursor is short lived. If the second call expires, report the error.
Finish with the echo JSON and a compact list of observed successes and errors.
Do not offer to make any changes."""


def settings_snapshot(profile):
    files = [
        profile / ".gemini/settings.json",
        profile / ".gemini/config/settings.json",
        profile / ".gemini/config/mcp_config.json",
        profile / ".gemini/antigravity-cli/settings.json",
    ]
    return {path.name + str(i): hashlib.sha256(path.read_bytes()).hexdigest()
            for i, path in enumerate(files) if path.is_file()}


def prompt(rpc, session_id, evidence):
    rpc.counter += 1
    prompt_id = rpc.counter
    rpc.send({"jsonrpc": "2.0", "id": prompt_id, "method": "session/prompt",
              "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": PROMPT}]}})
    deadline = time.monotonic() + 100
    update_names = {}
    chunks = []
    while True:
        try:
            line = rpc.lines.get(timeout=max(0, deadline - time.monotonic()))
        except Empty as exc:
            raise RpcFailure("Signed-in synthetic prompt timed out") from exc
        if line is None:
            raise RpcFailure("ACP closed before the synthetic prompt completed")
        frame = json.loads(line)
        if frame.get("id") == prompt_id and ("result" in frame or "error" in frame):
            if "error" in frame:
                err = frame["error"]
                evidence["promptError"] = {"code": err.get("code"), "message": str(err.get("message"))[:160]}
            else:
                evidence["stopReason"] = frame["result"].get("stopReason")
            evidence["reply"] = "".join(chunks)[-3000:]
            return
        params = frame.get("params", {})
        if frame.get("method") == "session/update":
            update = params.get("update", {})
            if update.get("sessionUpdate") == "agent_message_chunk":
                if update.get("content", {}).get("type") == "text":
                    chunks.append(update["content"].get("text", ""))
            if update.get("sessionUpdate") in ("tool_call", "tool_call_update"):
                tool_id = update.get("toolCallId")
                title = update.get("name") or update.get("title")
                if isinstance(title, str):
                    update_names[tool_id] = title
            continue
        if "method" not in frame or "id" not in frame:
            continue
        if frame["method"] == "session/request_permission":
            tool_call = params.get("toolCall", {})
            title = tool_call.get("name") or tool_call.get("title") or update_names.get(tool_call.get("toolCallId"), "")
            found = sorted(name for name in TOOLS if re.search(rf"(?<![a-z0-9]){name}(?![a-z0-9])", title))
            options = params.get("options", [])
            limited = next((opt for opt in options if opt.get("kind") == "allow_once"), None)
            granted = len(found) == 1 and limited is not None
            decision = {"outcome": "selected", "optionId": limited["optionId"]} if granted else {"outcome": "cancelled"}
            evidence.setdefault("permissions", []).append({"tool": found[0] if len(found) == 1 else None,
                                                          "allowOnce": granted})
            result = {"jsonrpc": "2.0", "id": frame["id"], "result": {"outcome": decision}}
        else:
            result = {"jsonrpc": "2.0", "id": frame["id"], "error": {
                "code": -32601, "message": "Host method not enabled for synthetic probe"}}
        rpc.send(result)


def main():
    runs = BASE / "runs"
    runs.mkdir(exist_ok=True)
    record = Path(mkdtemp(prefix="stage-0b-agy-live-", dir=runs))
    workspace = record / "empty-workspace"
    workspace.mkdir()
    profile = Path(os.environ["USERPROFILE"])
    exe = Path(os.environ["LOCALAPPDATA"]) / "agy/bin/agy.exe"
    existing = profile / ".gemini/config/mcp_config.json"
    if existing.is_file() and json.loads(existing.read_text(encoding="utf-8-sig").strip() or "{}").get("mcpServers"):
        raise SystemExit("The active user profile has other MCP servers. Use the disconnected fixture.")
    before = settings_snapshot(profile)
    env = isolated_env(record)
    for key in ("USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA"):
        if key in os.environ:
            env[key] = os.environ[key]
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "GOOGLE_APPLICATION_CREDENTIALS"):
        env.pop(key, None)
    args = [str(exe), "acp", "--stdio", "--disable-telemetry", "--sandbox",
            "--include-default-customizations=false", "--app-data-dir", record.name]
    evidence = {"probe_sha256": hashlib.sha256((BASE / "probe.py").read_bytes()).hexdigest(),
                "expectedEcho": ECHO, "inference": "Existing user-initiated sign-in"}
    print(f"record_directory={record}", flush=True)
    with (record / "live-acp.stderr.log").open("w", encoding="utf-8") as errors:
        rpc = ProcessRpc(args, workspace, env, errors)
        try:
            result = rpc.call("initialize", {"protocolVersion": 1, "clientCapabilities": {},
                                             "clientInfo": {"name": "wpai-stage-0b", "version": "1"}})
            evidence["acpVersion"] = result.get("protocolVersion")
            entry = {"name": LABEL, **definition(record, "agy-live"), "env": []}
            session = rpc.call("session/new", {"cwd": str(workspace), "mcpServers": [entry]}, timeout=18)
            evidence["ephemeralFixtureSession"] = bool(session.get("sessionId"))
            prompt(rpc, session["sessionId"], evidence)
        except (RpcFailure, OSError, KeyError, ValueError) as exc:
            evidence["driverError"] = str(exc)[:180]
        finally:
            evidence["process"] = rpc.close()
    evidence["existingSettingsUnchanged"] = before == settings_snapshot(profile)
    evidence["wire"] = trace_events(record / "agy-live.wire.jsonl")
    as_json(record / "agy-live.json", evidence)
    print(json.dumps(evidence, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()

"""Run a single authorized synthetic agent trial and retain only selected evidence."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
from uuid import uuid4

from benchmark import BENCH, parse, prepare, prompt, score


SERVER = "wpai_benchmark"
TOOLS = {"control": "fixture_read_field_v1", "treatment": "repo_health_v1"}
SAFE_ENV = ("SystemRoot", "WINDIR", "ComSpec", "PATH", "PATHEXT", "ProgramFiles", "ProgramFiles(x86)",
            "ProgramData", "PROCESSOR_ARCHITECTURE", "SystemDrive", "NUMBER_OF_PROCESSORS", "PUBLIC")
ACCOUNT_ENV = ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOME", "USERNAME", "USERDOMAIN")
MAX_STREAM = 2 * 1024 * 1024
RUN_SECONDS = 210
GROK_ROUTING = ("For the synthetic MCP operation named in the benchmark task, use Grok's use_tool wrapper with "
                "the exact operation name prefixed by wpai_benchmark__ and pass the input JSON inline. "
                "The task already names the tool. Do not use a built-in search or read tool to locate it.")


class Blocked(Exception):
    """A shareable preflight or client infrastructure disposition."""


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def execution_env(path):
    return {**{key: os.environ[key] for key in (*SAFE_ENV, *ACCOUNT_ENV) if key in os.environ},
            "TEMP": str(path), "TMP": str(path), "GIT_TERMINAL_PROMPT": "0"}


def server_args(path, arm):
    # No Python module, script path or target comes from an agent argument.
    return ["-B", "-s", str(path / "server/server.py"), arm, str(path / "trace.jsonl")]


def status(args, cwd, env, code):
    try:
        result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=18)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked(code) from exc
    if result.returncode:
        raise Blocked(code)
    return (result.stdout + result.stderr).decode("utf-8", "replace")


class Child:
    def __init__(self, args, cwd, env, stdin=True):
        self.lines = Queue()
        self.stderr = []
        self.overflow = threading.Event()
        self.process = subprocess.Popen(args, cwd=cwd, env=env,
                                        stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.pumps = [threading.Thread(target=self.capture, args=(stream, dest), daemon=True)
                      for stream, dest in ((self.process.stdout, self.lines), (self.process.stderr, None))]
        for pump in self.pumps:
            pump.start()

    def capture(self, stream, dest):
        count = 0
        try:
            while line := stream.readline(MAX_STREAM + 1):
                count += len(line)
                if count > MAX_STREAM:
                    self.overflow.set()
                    return
                if dest is None:
                    self.stderr.append(line)
                else:
                    dest.put(line)
        finally:
            if dest is not None:
                dest.put(None)

    def put(self, frame):
        self.process.stdin.write(json.dumps(frame, ensure_ascii=True).encode() + b"\n")
        self.process.stdin.flush()

    def read(self, deadline):
        if self.overflow.is_set():
            raise Blocked("client_stream_cap")
        try:
            line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
        except Empty as exc:
            raise Blocked("client_timeout") from exc
        if line is None:
            return None
        try:
            return json.loads(line)
        except ValueError as exc:
            raise Blocked("client_non_json_frame") from exc

    def finish(self):
        forced = False
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            forced = True
            self.process.kill()
            self.process.wait(timeout=5)
        for thread in self.pumps:
            thread.join(2)
        self.process.stdout.close()
        self.process.stderr.close()
        return {"exit_code": self.process.returncode, "forced": forced}


def recognized_calls(data, tool):
    if not isinstance(data, str) or re.match(r"(?i)\s*(?:read|write|edit|search|run command|terminal|browser)\b", data):
        return False
    # ACP display titles may decorate the exact operation token with a server name and arguments.
    # ACP receives one registered server, and the fixture independently exports only this operation.
    token = r"[_ -]".join(tool.split("_"))
    qualified = rf"(?:mcp_{{1,2}})?{SERVER}(?:_{{1,2}}|[ /.:\-]+){token}"
    return bool(re.search(rf"(?i)(?<![\w])(?:{qualified}|{token})(?![\w])", data))


def public_model(value):
    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9._-]{2,64}", value):
        return value
    return "unavailable"


def numeric_usage(value):
    return {key: item for key, item in value.items() if isinstance(key, str) and len(key) < 64
            and not isinstance(item, bool) and isinstance(item, (int, float))}


def codex(path, arm, evidence):
    exe = shutil.which("codex.exe")
    if not exe:
        raise Blocked("codex_unavailable")
    env = execution_env(path)
    stock = Path(os.environ.get("CODEX_HOME", Path(os.environ["USERPROFILE"]) / ".codex")) / "auth.json"
    home = path / "codex-home"
    home.mkdir()
    auth = home / "auth.json"
    if not stock.is_file():
        raise Blocked("existing_codex_auth_file_unavailable")
    before = sha256(stock.read_bytes()).digest()
    try:
        auth.symlink_to(stock)
    except OSError as exc:
        raise Blocked("isolated_codex_credential_reference_unavailable") from exc
    env["CODEX_HOME"] = str(home)
    workspace = path / "workspace"
    child = None
    try:
        auth_status = status([exe, "login", "status"], workspace, env, "codex_existing_login_unavailable")
        if "Logged in using ChatGPT" not in auth_status:
            raise Blocked("codex_existing_subscription_not_established")
        evidence["auth_category"] = "existing ChatGPT subscription"
        evidence["client_version"] = status([exe, "--version"], workspace, env, "codex_version").strip()
        tool, model = TOOLS[arm], "gpt-6.1-sol"
        evidence["requested_model"] = model
        evidence["reasoning_setting"] = "low"
        config = "\n".join([
            'approval_policy = "never"', 'sandbox_mode = "read-only"', 'web_search = "disabled"',
            'forced_login_method = "chatgpt"', 'model_provider = "openai"', 'model_reasoning_effort = "low"',
            'project_doc_max_bytes = 0', '[features]', 'apps = false', 'hooks = false', 'memories = false',
            'multi_agent = false', 'shell_tool = false', 'mcp_2026_07_28 = true', f'[mcp_servers.{SERVER}]',
            f'command = {json.dumps(sys.executable)}', f'args = {json.dumps(server_args(path, arm))}',
            f'enabled_tools = ["{tool}"]', 'required = true', 'startup_timeout_sec = 12', 'tool_timeout_sec = 16',
        ])
        (home / "config.toml").write_text(config, encoding="utf-8")
        listing = json.loads(status([exe, "mcp", "list", "--json"], workspace, env, "codex_mcp_preflight"))
        if not isinstance(listing, list) or [entry["name"] for entry in listing if entry.get("enabled", True)] != [SERVER]:
            raise Blocked("codex_other_mcp_server_or_missing_fixture")
        evidence["isolation"] = {"only_mcp_server": SERVER, "only_mcp_tool": tool, "shell_disabled": True,
                                 "apps_hooks_memory_subagents_web_disabled": True,
                                 "credentials_source_referenced_not_copied": True}
        args = [exe, "exec", "--ephemeral", "--ignore-rules", "--skip-git-repo-check", "--color", "never",
                "--json", "-m", model, prompt(arm)]
        evidence["model_prompt_started"] = True
        child = Child(args, workspace, env, stdin=False)
        deadline = time.monotonic() + RUN_SECONDS
        calls = []
        completed = []
        non_fixture = []
        messages = []
        turns = 0
        while event := child.read(deadline):
            kind = event.get("type")
            item = event.get("item", {})
            if kind == "turn.started":
                turns += 1
            if kind == "turn.completed":
                evidence["usage"] = numeric_usage(event.get("usage", {}))
            if kind in ("item.started", "item.completed") and item.get("type") == "mcp_tool_call":
                row = {"is_fixture": item.get("tool") == tool and item.get("server") == SERVER,
                       "status": item.get("status"), "has_result": item.get("result") is not None}
                (calls if kind == "item.started" else completed).append(row)
            if kind == "item.started" and item.get("type") in ("command_execution", "file_change", "web_search"):
                non_fixture.append(item["type"])
            if kind == "item.completed" and item.get("type") == "agent_message":
                messages.append(item.get("text", ""))
            if kind in ("error", "turn.failed"):
                evidence["client_error_event"] = True
        banner = b"".join(child.stderr).decode("utf-8", "replace")
        match = re.search(r"(?mi)^model:\s*([a-z0-9._-]+)\s*$", banner)
        evidence.update(model=public_model(match[1]) if match else model, model_identity_source="client banner" if match else "pinned CLI model selection",
                        model_calls="unavailable", agent_turns=turns, client_tool_starts=calls,
                        client_tool_results=completed, out_of_scope_tool_events=non_fixture)
        return messages[-1] if messages else None
    finally:
        if child:
            evidence["client_process"] = child.finish()
        evidence["normal_auth_file_unchanged"] = sha256(stock.read_bytes()).digest() == before
        if auth.is_symlink():
            auth.unlink()


def model_from_session(session):
    models = session.get("models", {})
    if isinstance(models, dict) and models.get("currentModelId"):
        return public_model(models["currentModelId"])
    for option in session.get("configOptions", []):
        if option.get("category") == "model" or option.get("id") == "model":
            return public_model(option.get("currentValue"))
    return "unavailable"


def antigravity(path, arm, evidence):
    exe = Path(os.environ["LOCALAPPDATA"]) / "agy/bin/agy.exe"
    if not exe.is_file():
        raise Blocked("antigravity_unavailable")
    tool = TOOLS[arm]
    env = execution_env(path)
    workspace = path / "workspace"
    gemini_home = Path(os.environ["USERPROFILE"]) / ".gemini"
    settings = [gemini_home / name for name in ("settings.json", "config/settings.json", "config/mcp_config.json",
                                               "antigravity-cli/settings.json")]
    before = {p: sha256(p.read_bytes()).digest() for p in settings if p.is_file()}
    for item in settings:
        if item.is_file():
            data = parse(item.read_text(encoding="utf-8-sig").strip() or "{}")
            if data.get("mcpServers") or data.get("permissions", {}).get("allow"):
                raise Blocked("antigravity_stock_permissions_or_mcp_overlap")
    evidence["client_version"] = status([str(exe), "--version"], workspace, env, "antigravity_version").strip()
    state_name = "wpai-benchmark-" + uuid4().hex
    state = gemini_home / state_name
    if state.exists():
        raise Blocked("antigravity_disposable_state_collision")
    args = [str(exe), "acp", "--stdio", "--disable-telemetry", "--sandbox", "--include-default-customizations=false",
            "--app-data-dir", state_name, "--log-file", str(path / "agy-acp.log")]
    child = Child(args, workspace, env)
    titles, chunks = {}, []
    decisions, operations = [], {}
    out_of_scope = []

    def answer(frame):
        params = frame.get("params", {})
        method = frame.get("method")
        if method == "session/update":
            update = params.get("update", {})
            kind = update.get("sessionUpdate")
            content = update.get("content", {})
            if kind == "agent_message_chunk" and isinstance(content, dict) and content.get("type") == "text":
                chunks.append(content.get("text", ""))
            if kind in ("agent_message_chunk", "agent_thought_chunk", "tool_call", "tool_call_update", "usage_update"):
                model = public_model(update.get("modelId"))
                if model != "unavailable":
                    evidence["model"] = model
                    evidence["model_identity_source"] = "ACP update"
            if kind == "usage_update" and isinstance(update.get("usage"), dict):
                evidence["usage"] = numeric_usage(update["usage"])
            if kind in ("tool_call", "tool_call_update"):
                call = update.get("toolCallId")
                if not isinstance(call, str):
                    return
                title = update.get("name") or update.get("title")
                if title:
                    titles[call] = title
                prior = operations.get(call, {})
                operations[call] = {"is_fixture": recognized_calls(titles.get(call), tool),
                                    "status": update.get("status", prior.get("status")),
                                    "has_result": bool(update.get("rawOutput") or update.get("content")) or prior.get("has_result", False)}
            return
        if "id" not in frame or "method" not in frame:
            return
        response = {"jsonrpc": "2.0", "id": frame["id"]}
        if method == "session/request_permission":
            call = params.get("toolCall", {})
            raw = call.get("rawInput")
            raw = raw if isinstance(raw, dict) else {}
            names = (call.get("name"), call.get("title"), titles.get(call.get("toolCallId")),
                     raw.get("name"), raw.get("toolName"))
            limited = next((option for option in params.get("options", []) if option.get("kind") == "allow_once"), None)
            matched = any(recognized_calls(name, tool) for name in names)
            scoped = matched and limited is not None
            decisions.append({"fixture_match": matched, "allow_once_available": limited is not None,
                              "decision": "allow_once" if scoped else "cancelled",
                              "kind": call.get("kind") if call.get("kind") in ("read", "edit", "execute", "other", "mcp") else "unavailable",
                              "server_label_present": any(isinstance(name, str) and SERVER in name for name in names)})
            response["result"] = {"outcome": {"outcome": "selected", "optionId": limited["optionId"]} if scoped
                                   else {"outcome": "cancelled"}}
        else:
            out_of_scope.append("host_side_method_denied")
            response["error"] = {"code": -32601, "message": "No host filesystem or terminal access for this fixture"}
        child.put(response)

    def exchange(request_id, method, params, seconds):
        child.put({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + seconds
        while (frame := child.read(deadline)) is not None:
            if frame.get("id") == request_id and ("result" in frame or "error" in frame):
                if "error" in frame:
                    evidence["client_error_code"] = frame["error"].get("code")
                    msg = str(frame["error"].get("message", "")).lower()
                    evidence["client_error_category"] = next((label for label, words in (
                        ("authentication", ("auth", "sign in", "login")),
                        ("quota", ("quota", "rate limit", "exhaust")),
                        ("path", ("path", "relative", "absolute")),
                        ("sandbox", ("sandbox",)),
                    ) if any(word in msg for word in words)), "unclassified")
                    raise Blocked(f"antigravity_{method.replace('/', '_')}_rejected")
                return frame["result"]
            answer(frame)
        raise Blocked(f"antigravity_{method.replace('/', '_')}_disconnected")

    try:
        ready = exchange(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {},
                                            "clientInfo": {"name": "wpai-synthetic-benchmark", "version": "1"}}, 20)
        evidence["acp_version"] = ready.get("protocolVersion")
        registered = {"name": SERVER, "command": sys.executable, "args": server_args(path, arm), "env": []}
        session = exchange(2, "session/new", {"cwd": str(workspace), "mcpServers": [registered]}, 30)
        evidence["auth_category"] = "existing signed-in Google Antigravity session"
        evidence["model"] = model_from_session(session)
        evidence["model_identity_source"] = "ACP session current model" if evidence["model"] != "unavailable" else "unavailable"
        evidence["isolation"] = {"only_mcp_server": SERVER, "only_mcp_tool": tool, "terminal_sandbox": True,
                                 "customizations_disabled": True, "host_methods_denied": True, "permission_decisions": decisions}
        if not session.get("sessionId") or evidence["model"] == "unavailable":
            raise Blocked("antigravity_effective_model_or_session_unavailable")
        evidence["model_prompt_started"] = True
        started = time.monotonic()
        final = exchange(3, "session/prompt", {"sessionId": session["sessionId"],
                                              "prompt": [{"type": "text", "text": prompt(arm)}]}, RUN_SECONDS)
        evidence["prompt_elapsed_seconds"] = round(time.monotonic() - started, 3)
        evidence["agent_turns"] = 1
        evidence["stop_reason"] = final.get("stopReason")
        if isinstance(final.get("usage"), dict):
            evidence["usage"] = numeric_usage(final["usage"])
        return "".join(chunks) if chunks else None
    finally:
        evidence["client_tool_starts"] = list(operations.values())
        evidence["client_tool_results"] = [item for item in operations.values() if item["status"] in ("completed", "failed")]
        evidence["out_of_scope_tool_events"] = out_of_scope
        evidence["client_process"] = child.finish()
        evidence["normal_settings_unchanged"] = before == {p: sha256(p.read_bytes()).digest() for p in settings if p.is_file()}
        if state.exists() and state.resolve().parent == gemini_home.resolve():
            shutil.rmtree(state)
        evidence["isolated_app_data_removed"] = not state.exists()


def grok(path, arm, evidence):
    exe = shutil.which("grok.exe")
    if not exe:
        raise Blocked("grok_unavailable")
    tool = TOOLS[arm]
    env = execution_env(path)
    stock = Path(os.environ["USERPROFILE"]) / ".grok/auth.json"
    if not stock.is_file() or not any(key.startswith("https://auth.x.ai::") for key in parse(stock.read_bytes())):
        raise Blocked("grok_existing_subscription_not_established")
    before = sha256(stock.read_bytes()).digest()
    home = path / "grok-home"
    home.mkdir()
    auth = home / "auth.json"
    try:
        auth.symlink_to(stock)
    except OSError as exc:
        raise Blocked("isolated_grok_credential_reference_unavailable") from exc
    workspace = path / "workspace"
    env.update(GROK_HOME=str(home), GROK_DISABLE_AUTOUPDATER="1")
    for harness in ("CLAUDE", "CURSOR"):
        for part in ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS"):
            env[f"GROK_{harness}_{part}_ENABLED"] = "0"
    (home / "trusted_folders.toml").write_text(f"[folders.{json.dumps(str(workspace))}]\ntrusted = true\n"
                                               f"decided_at = {int(time.time())}\n", encoding="utf-8")
    rule = f"MCPTool({SERVER}__{tool})"
    deny = ("Bash", "Read", "Edit", "Grep", "Glob", "WebFetch", "WebSearch")
    (home / "config.toml").write_text("\n".join([
        "[plugins]", 'disabled = ["cloudflare"]', "[permission]", f"allow = {json.dumps([rule])}",
        f"deny = {json.dumps(deny)}", f"[mcp_servers.{SERVER}]", f"command = {json.dumps(sys.executable)}",
        f"args = {json.dumps(server_args(path, arm))}", "startup_timeout_sec = 12", "tool_timeout_sec = 16",
    ]), encoding="utf-8")
    child = None
    try:
        config = json.loads(status([exe, "--no-auto-update", "inspect", "--json"], workspace, env, "grok_inspect"))
        if (not config.get("projectTrusted") or [x["name"] for x in config.get("mcpServers", [])] != [SERVER]
                or config.get("hooks") or any(p.get("enabled") for p in config.get("plugins", []))):
            raise Blocked("grok_isolated_workspace_not_trusted_or_tool_overlap")
        if any(not Path(item["path"]).resolve().is_relative_to(path) for item in config["configSources"]["layers"]
               if item.get("role") in ("user", "project")):
            raise Blocked("grok_loaded_normal_user_configuration")
        evidence["isolation"] = {"only_mcp_server": SERVER, "only_mcp_tool": tool, "permissions": "exact allow with dontAsk",
                                 "no_hooks_or_enabled_plugins": True, "credentials_source_referenced_not_copied": True}
        evidence["client_version"] = status([exe, "--no-auto-update", "--version"], workspace, env, "grok_version").strip()
        selection = status([exe, "--no-auto-update", "models"], workspace, env, "grok_existing_session_catalog_unavailable")
        if not re.search(r"\bgrok-4\.7\b", selection):
            raise Blocked("grok_required_model_not_in_current_catalog")
        evidence["auth_category"] = "existing xAI OAuth subscription session"
        evidence["requested_model"] = "grok-4.7"
        evidence["reasoning_setting"] = "low"
        evidence["client_routing_hint_sha256"] = sha256(GROK_ROUTING.encode()).hexdigest()
        args = [exe, "--no-auto-update", "--model", "grok-4.7", "--reasoning-effort", "low", "--permission-mode", "dontAsk",
                "--tools", "read_file", "--disable-web-search", "--no-memory", "--no-subagents", "--no-plan", "--max-turns", "26",
                "--verbatim", "--output-format", "streaming-json", "--session-id", str(uuid4()), "--prompt-file", str(path / "prompt.txt"),
                "--allow", rule, "--rules", GROK_ROUTING]
        for rule in deny:
            args.extend(("--deny", rule))
        calls, results, other, messages = [], [], [], []
        evidence["model_prompt_started"] = True
        began = time.monotonic()
        child = Child(args, workspace, env, stdin=False)
        deadline = began + RUN_SECONDS
        while event := child.read(deadline):
            kind = event.get("type")
            if kind == "tool_call":
                raw = event.get("rawInput", {})
                if event.get("toolName") == "use_tool" and raw.get("tool_name") == f"{SERVER}__{tool}":
                    calls.append({"is_fixture": True})
                elif event.get("toolName") in ("search_tool", "use_tool"):
                    other.append("unqualified_or_unapproved_" + event["toolName"])
                else:
                    other.append("non_fixture_tool_event")
                messages.clear()
            if kind == "tool_call_update":
                raw = event.get("rawOutput") or {}
                if raw.get("type") == "MCP" and raw.get("server_name") == SERVER and raw.get("tool_name") == tool:
                    results.append({"is_fixture": True, "has_result": True, "status": "failed" if raw.get("is_error") else "completed"})
                    messages.clear()
            if kind == "text" and isinstance(event.get("data"), str):
                messages.append(event["data"])
            if kind == "end":
                for key in ("usage", "tokenUsage"):
                    if isinstance(event.get(key), dict):
                        evidence["usage"] = numeric_usage(event[key])
                if isinstance(event.get("modelUsage"), dict):
                    evidence["models"] = {public_model(name): numeric_usage(usage) for name, usage in event["modelUsage"].items()
                                          if isinstance(usage, dict)}
                    if len(evidence["models"]) == 1:
                        evidence["model"] = next(iter(evidence["models"]))
                        evidence["model_identity_source"] = "Grok modelUsage"
                        evidence["model_calls"] = evidence["models"][evidence["model"]].get("modelCalls", "unavailable")
                evidence["agent_turns"] = event.get("num_turns", "unavailable")
                evidence["provider_reported_cost_usd"] = event.get("total_cost_usd", "unavailable")
                evidence["stop_reason"] = event.get("stopReason", evidence.get("stop_reason"))
        evidence["prompt_elapsed_seconds"] = round(time.monotonic() - began, 3)
        evidence["client_tool_starts"] = calls
        evidence["client_tool_results"] = results
        evidence["out_of_scope_tool_events"] = other
        return "".join(messages) if messages else None
    finally:
        if child:
            evidence["client_process"] = child.finish()
        evidence["normal_auth_file_unchanged"] = sha256(stock.read_bytes()).digest() == before
        if auth.is_symlink():
            auth.unlink()


def process_state(pid):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return "gone" if ctypes.get_last_error() == 87 else "unavailable"
    try:
        return {0: "gone", 258: "live"}.get(kernel.WaitForSingleObject(handle, 0), "unavailable")
    finally:
        kernel.CloseHandle(handle)


def server_evidence(path):
    log = path / "trace.jsonl"
    raw = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.is_file() else []
    starts = [row["pid"] for row in raw if row["event"] == "start"]
    for _ in range(15):
        states = [process_state(pid) for pid in starts]
        if "live" not in states:
            break
        time.sleep(0.1)
    return [{key: value for key, value in entry.items() if key != "pid"} for entry in raw], states


def run(provider, arm, destination):
    if destination.exists():
        raise SystemExit("Trial evidence already exists. Preserve it before a separately authorized retry.")
    evidence = {"provider": provider, "arm": arm, "auth_category": "unavailable",
                "model_prompt_started": False, "usage": "unavailable", "model_calls": "unavailable",
                "agent_turns": "unavailable", "model": "unavailable", "reasoning_setting": "unavailable",
                "quota_delta": "unavailable", "actual_billable_api_charge": "unavailable",
                "prompt_sha256": sha256(prompt(arm).encode()).hexdigest()}
    expected = parse((BENCH / "ground_truth.json").read_bytes())
    with TemporaryDirectory(prefix="wpai-synthetic-", dir=Path(os.environ["SystemRoot"]) / "Temp") as root:
        path = Path(root) / "trial"
        prepare(path, arm)
        start = time.monotonic()
        evidence["started_at"] = utc()
        answer = None
        try:
            answer = {"codex": codex, "antigravity": antigravity, "grok": grok}[provider](path, arm, evidence)
        except (Blocked, OSError, ValueError, TimeoutError) as exc:
            evidence["blocked"] = str(exc) if isinstance(exc, Blocked) else type(exc).__name__
        evidence["finished_at"] = utc()
        evidence["run_elapsed_seconds"] = round(time.monotonic() - start, 3)
        trace, states = server_evidence(path)
        evidence["server_trace"] = trace
        evidence["server_processes"] = states
        if "live" in states:
            raise SystemExit("Fixture process still running; preserve the existing run for recovery.")
        evidence["server_protocols"] = sorted({row["protocol"] for row in trace
                                                  if row["event"] == "sent" and row.get("protocol")})
        evidence["final_response_received"] = answer is not None
        if answer is not None:
            evidence["answer_score"] = score(answer, expected)
            if evidence["answer_score"]["passed"]:
                evidence["validated_answer"] = parse(answer)
        calls = [row for row in trace if row["event"] == "acquisition"]
        replies = [row for row in trace if row["event"] == "sent" and row["method"] == "tools/call"]
        evidence["server_metrics"] = {"operations": len(calls), "statuses": dict(Counter(row["status"] for row in calls)),
                                      "process_attempts": sum(row["process_attempts"] for row in calls),
                                      "json_bytes": sum(row["report_json_bytes"] for row in replies),
                                      "rpc_wire_bytes": sum(row["wire_bytes"] for row in replies),
                                      "acquisition_ms": round(sum(row["acquisition_ms"] for row in calls), 4),
                                      "round_trip_ms": round(sum(row["round_trip_ms"] for row in replies), 4),
                                      "serialization_ms": round(sum(row["serialization_ms"] for row in trace
                                                                     if row["event"] == "serialization"), 4)}
    evidence["temporary_directory_removed"] = not path.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: evidence.get(key) for key in ("provider", "arm", "blocked", "server_protocols",
                      "server_metrics", "client_process", "answer_score")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("codex", "antigravity", "grok"))
    parser.add_argument("arm", choices=tuple(TOOLS))
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    run(args.provider, args.arm, args.destination)

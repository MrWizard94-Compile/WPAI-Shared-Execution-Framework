"""Verify graceful MCP disconnect for Grok's native ACP model route."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
from threading import Thread
import time

BASE = Path(__file__).resolve().parent
RUN = BASE / "runs/stage-0c-zmxauqt5"
EXPECTED = {"value": {"label": "WPAI", "count": 7, "enabled": True}}
HASHES = {
    "probe.py": "d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770",
    "launch_probe.py": "766a332abdd72e8233267796e2961f8b1cbc2fa9d875c656891f76bcdff32683",
}
ALLOWED = ("probe_info", "probe_echo", "probe_validation", "probe_evidence_page", "probe_denied_operation")
DENIED = ("Bash", "Read", "Edit", "Grep", "WebFetch", "WebSearch")
VERSION = "grok 1.0.92 (b06756fd6256) [stable]"
PROMPT = """Use only the MCP dispatcher use_tool with {"tool_name":"wpai_probe__probe_echo",
"tool_input":{"value":{"label":"WPAI","count":7,"enabled":true}}}. That qualified key is
already known. Do not search or use any other tool. Return the exact echo JSON you received."""


def check_artifact():
    for name, expected in HASHES.items():
        if sha256((BASE/name).read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Stage 0B artifact mismatch: {name}")


def child_env():
    env = os.environ.copy()
    for key in ("XAI_API_KEY", "GROK_API_KEY", "GROK_XAI_API_BASE_URL",
                "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL"):
        env.pop(key, None)
    env["GROK_DISABLE_AUTOUPDATER"] = "1"
    for product, kinds in (("CLAUDE", ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS")),
                           ("CURSOR", ("SKILLS", "RULES", "AGENTS", "MCPS", "HOOKS"))):
        for key in kinds:
            env[f"GROK_{product}_{key}_ENABLED"] = "0"
    return env


def scopes():
    user = Path(os.environ["USERPROFILE"])/".grok"
    names = ("config.toml", "requirements.toml", "managed_config.toml")
    return {name: sha256((user/name).read_bytes()).hexdigest() if (user/name).is_file() else None
            for name in names}


class Rpc:
    def __init__(self, proc, evidence):
        self.process = proc
        self.evidence = evidence
        self.incoming = Queue()
        self.next_id = 0
        Thread(target=self.reader, daemon=True).start()

    def reader(self):
        try:
            for line in self.process.stdout:
                self.incoming.put(json.loads(line))
        except (ValueError, OSError):
            self.incoming.put(RuntimeError("Grok ACP produced invalid JSONL"))
        finally:
            self.incoming.put(None)

    def send(self, frame):
        self.process.stdin.write(json.dumps(frame, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def call(self, method, params, timeout=12):
        self.next_id += 1
        target_id = self.next_id
        self.send({"jsonrpc": "2.0", "id": target_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            try:
                frame = self.incoming.get(timeout=max(0, deadline - time.monotonic()))
            except Empty:
                raise RuntimeError(f"{method} timed out") from None
            if frame is None:
                raise RuntimeError(f"Grok ACP exited while awaiting {method}")
            if isinstance(frame, Exception):
                raise frame
            response_method = frame.get("method")
            if response_method and "id" in frame:
                params = frame.get("params", {})
                data = params.get("toolCall", {})
                self.evidence.setdefault("agentRequests", []).append({
                    "method": response_method,
                    "tool": data.get("title"),
                })
                if response_method == "session/request_permission":
                    self.send({"jsonrpc": "2.0", "id": frame["id"],
                               "result": {"outcome": {"outcome": "cancelled"}}})
                else:
                    self.send({"jsonrpc": "2.0", "id": frame["id"],
                               "error": {"code": -32601, "message": "Not enabled in this fixture"}})
                continue
            if response_method == "session/update":
                update = frame.get("params", {}).get("update", {})
                kind = update.get("sessionUpdate")
                if kind in ("tool_call", "tool_call_update"):
                    fields = ("sessionUpdate","toolCallId","title","status","rawInput","rawOutput","content")
                    self.evidence.setdefault("toolEvents", []).append({k: update[k] for k in fields if k in update})
                if kind == "agent_message_chunk":
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        self.evidence["reply"] = (self.evidence.get("reply", "") + content.get("text", ""))[-2400:]
                continue
            if frame.get("id") == target_id:
                if "error" in frame:
                    raise RuntimeError(f"{method}: {frame['error']}")
                return frame.get("result", {})


def main():
    check_artifact()
    path = RUN / "grok-acp-model-close.json"
    wire = RUN / "grok-acp-model-close.wire.jsonl"
    if path.exists() or wire.exists():
        raise SystemExit("Lifecycle attempt already exists. Preserve it before another run.")
    project = RUN / "grok"
    config = project / ".grok/config.toml"
    exact = config.read_bytes()
    revised = exact.replace(b'"grok-qualified"]', b'"grok-acp-model-close"]')
    if revised == exact:
        raise SystemExit("Unexpected current disposable config")
    exe = shutil.which("grok.exe")
    env = child_env()
    version = subprocess.check_output([exe,"--no-auto-update","--version"],text=True,env=env).strip()
    if version != VERSION:
        raise SystemExit(f"Unexpected installed Grok version: {version}")
    args = [exe,"--no-auto-update","--permission-mode","dontAsk","--no-subagents",
            "--no-memory","--no-plan","--disable-web-search"]
    for name in ALLOWED:
        args.extend(("--allow",f"MCPTool(wpai_probe__{name})"))
    for name in DENIED:
        args.extend(("--deny",name))
    args.extend(("agent","--no-leader","--model","grok-4.7","--reasoning-effort","low","stdio"))
    evidence = {"version":version, "timestampUTC":datetime.now(timezone.utc).isoformat(),
                "argv":args,"artifact":HASHES,"configSHA256":sha256(revised).hexdigest(),
                "prompt":PROMPT,"requestedModel":"grok-4.7"}
    before = scopes()
    session_id = None
    started = time.monotonic()
    try:
        config.write_bytes(revised)
        check = subprocess.run([exe,"--no-auto-update","inspect","--json"],cwd=project,
                               env=env,capture_output=True,text=True,encoding="utf-8",timeout=10,check=True)
        result = json.loads(check.stdout)
        shape = [(m["name"],m["transport"]) for m in result["mcpServers"]]
        assert result["projectTrusted"] and shape == [("wpai_probe","stdio")]
        assert not result["hooks"] and not any(p["enabled"] for p in result["plugins"])
        evidence["launchScope"] = {"trusted":True,"servers":shape,"activePlugins":0,"hooks":0}
        with (RUN/"grok-acp-model-close.stderr.txt").open("w",encoding="utf-8") as err:
            proc = subprocess.Popen(args,cwd=project,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                    stderr=err,text=True,encoding="utf-8")
            rpc = Rpc(proc, evidence)
            try:
                init = rpc.call("initialize",{
                    "protocolVersion":1,"clientCapabilities":{},
                    "clientInfo":{"name":"wpai-stage-0c-lifecycle","version":"1"}})
                caps = init.get("agentCapabilities",{}).get("sessionCapabilities",{})
                auth_ids = [item["id"] for item in init.get("authMethods",[])]
                evidence.update(acpSessionCapabilities=caps, authMethods=auth_ids)
                if "close" not in caps or "cached_token" not in auth_ids:
                    raise RuntimeError("Installed agent did not advertise session close and cached OAuth")
                rpc.call("authenticate",{"methodId":"cached_token","_meta":{"headless":True}})
                evidence["authRoute"] = "Existing cached xAI OAuth"
                session = rpc.call("session/new",{"cwd":str(project),"mcpServers":[],
                    "_meta":{"yoloMode":False,"autoMode":False}})
                session_id = session["sessionId"]
                modes = session.get("modes") or {}
                current = modes.get("currentModeId")
                ids = [item["id"] for item in modes.get("availableModes",[])]
                evidence["modes"] = {"initial":current,"available":ids}
                evidence["configOptionIds"] = [option.get("id") for option in session.get("configOptions",[])]
                if current != "dontAsk":
                    if "dontAsk" not in ids:
                        raise RuntimeError("ACP did not expose a verifiable deny-by-default permission mode")
                    rpc.call("session/set_mode",{"sessionId":session_id,"modeId":"dontAsk"})
                evidence["testMode"] = "dontAsk"
                result = rpc.call("session/prompt",{"sessionId":session_id,
                    "prompt":[{"type":"text","text":PROMPT}]},timeout=43)
                evidence["promptResult"] = {"stopReason":result.get("stopReason")}
                for key in ("usage","modelUsage","costUsdTicks","model"):
                    if key in (result.get("_meta") or {}):
                        evidence["promptResult"][key] = result["_meta"][key]
            except (AssertionError, KeyError, OSError, RuntimeError) as exc:
                evidence["failure"] = str(exc)
            finally:
                if session_id is not None:
                    try:
                        response = rpc.call("session/close",{"sessionId":session_id},timeout=10)
                        evidence["sessionCloseReply"] = response
                        end = time.monotonic() + 5
                        while time.monotonic() < end:
                            if wire.exists() and '"reason":"eof"' in wire.read_text(encoding="utf-8"):
                                evidence["eofBeforeTransportClose"] = True
                                break
                            time.sleep(0.1)
                    except (RuntimeError, OSError) as exc:
                        evidence["sessionCloseFailure"] = str(exc)
                proc.stdin.close()
                try:
                    evidence["exit"] = proc.wait(timeout=10)
                    evidence["forced"] = False
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    evidence["exit"] = proc.wait(timeout=5)
                    evidence["forced"] = True
    finally:
        config.write_bytes(exact)
        check_artifact()
        evidence["normalConfigUnchanged"] = scopes() == before
        evidence["seconds"] = round(time.monotonic()-started,3)
        evidence["wire"] = [json.loads(line) for line in wire.read_text(encoding="utf-8").splitlines()] if wire.exists() else []
        path.write_text(json.dumps(evidence,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({key:value for key,value in evidence.items() if key not in {"argv","prompt","toolEvents","reply"}}),flush=True)


if __name__ == "__main__":
    main()

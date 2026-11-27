"""Run Stage 0C Grok using the already approved disposable project and existing OAuth login."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

BASE = Path(__file__).resolve().parent
PROBE_SHA = "d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770"
LAUNCH_SHA = "766a332abdd72e8233267796e2961f8b1cbc2fa9d875c656891f76bcdff32683"
NAMES = (
    "probe_info", "probe_echo", "probe_validation",
    "probe_evidence_page", "probe_denied_operation",
)
DENY = ("Bash", "Read", "Edit", "Grep", "WebFetch", "WebSearch")
PROMPT = """Use the MCP dispatcher use_tool exactly once with the known qualified key wpai_probe__probe_echo, inline tool_input {"value":{"label":"WPAI","count":7,"enabled":true}}. Do not do tool search or use any other tool. Return the exact JSON received."""


def assert_artifact():
    for file, digest in (("probe.py", PROBE_SHA), ("launch_probe.py", LAUNCH_SHA)):
        if sha256((BASE/file).read_bytes()).hexdigest() != digest:
            raise SystemExit(f"Stop: accepted artifact mismatch for {file}")


def snapshot():
    conf = Path(os.environ["USERPROFILE"]) / ".grok"
    return {name: sha256((conf/name).read_bytes()).hexdigest() if (conf/name).is_file() else None
            for name in ("config.toml", "requirements.toml", "managed_config.toml")}


def child_env():
    env = os.environ.copy()
    for key in ("XAI_API_KEY", "GROK_API_KEY", "GROK_XAI_API_BASE_URL",
                "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL"):
        env.pop(key, None)
    for harness, sections in (("CLAUDE", ("SKILLS","RULES","AGENTS","MCPS","HOOKS")),
                              ("CURSOR", ("SKILLS","RULES","AGENTS","MCPS","HOOKS"))):
        for part in sections:
            env[f"GROK_{harness}_{part}_ENABLED"] = "0"
    env["GROK_DISABLE_AUTOUPDATER"] = "1"
    return env


def process_observer(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return kernel, handle


def read_process(observer, wait_ms):
    kernel, handle = observer
    signal = kernel.WaitForSingleObject(handle, wait_ms)
    if signal == 0x102:
        return {"exited": False}
    if signal != 0:
        raise ctypes.WinError(ctypes.get_last_error())
    code = wintypes.DWORD()
    if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {"exited": True, "exitCode": code.value}


def exercise():
    assert_artifact()
    if len(sys.argv) != 2:
        raise SystemExit("Usage: stage_0c_grok.py RUN_DIRECTORY")
    record = Path(sys.argv[1]).resolve()
    if not record.is_relative_to(BASE / "runs") or not record.name.startswith("stage-0c-"):
        raise SystemExit("Run directory must be inside the Stage 0C fixture")
    workdir = record / "grok"
    config = workdir / ".grok/config.toml"
    cfg = config.read_text(encoding="utf-8")
    cfg = cfg.replace(f'{json.dumps(str(record))}, "grok-qualified"]', f'{json.dumps(str(record))}, "grok-headless-close"]')
    if '"grok-headless-close"]' not in cfg:
        raise SystemExit("The disposable project does not have the expected launcher arguments")
    if cfg != config.read_text(encoding="utf-8"):
        config.write_text(cfg, encoding="utf-8")
    if (record / "grok-headless-close.result.json").exists() or (record / "grok-headless-close.wire.jsonl").exists():
        raise SystemExit("Prior invocation evidence exists; preserve it before starting another attempt")
    grok = shutil.which("grok.exe")
    env = child_env()
    preflight = subprocess.run([grok, "--no-auto-update", "inspect", "--json"], cwd=workdir, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=12, check=True)
    v = json.loads(preflight.stdout)
    effective = v["permissions"]
    skipped = effective.get("skipped") or []
    pre = {"trusted": v["projectTrusted"], "managedOnly": effective["mcpManagedServersOnly"],
           "mcpServers": [{"name": item["name"], "transport": item["transport"]} for item in v["mcpServers"]],
           "hooks": len(v["hooks"]), "enabledPlugins": [x["name"] for x in v["plugins"] if x["enabled"]],
           "ruleCount": effective["loaded"], "fixtureRuleSkips": sum(
               "wpai_probe" in item.get("rule","") for item in skipped)}
    (record/"grok-headless-close.preflight.json").write_text(json.dumps(pre,indent=2), encoding="utf-8")
    if not(pre["trusted"] and pre["mcpServers"] == [{"name":"wpai_probe", "transport":"stdio"}]
           and not pre["hooks"] and not pre["enabledPlugins"] and not pre["fixtureRuleSkips"]):
        raise SystemExit(json.dumps({"preflightBlocked":pre}))
    version = subprocess.check_output([grok,"--no-auto-update","--version"],text=True,env=env).strip()
    if not version.startswith("grok 1.0.92 "):
        raise SystemExit(f"Unexpected version: {version}")
    prompt_path = record / "grok-headless-close.prompt.txt"
    prompt_path.write_text(PROMPT,encoding="utf-8")
    session = str(uuid.uuid4())
    args = [
        grok,"--no-auto-update","--model","grok-4.7","--reasoning-effort","low",
        "--permission-mode","dontAsk","--tools","read_file",
        "--disable-web-search","--no-memory","--no-subagents","--no-plan",
        "--max-turns","4","--verbatim","--output-format","streaming-json",
        "--session-id",session,"--prompt-file",str(prompt_path),
    ]
    for name in NAMES:
        args.extend(("--allow",f"MCPTool(wpai_probe__{name})"))
    for rule in DENY:
        args.extend(("--deny",rule))
    result = {
        "timestampUTC":datetime.now(timezone.utc).isoformat(), "version": version,
        "requestedModel":"grok-4.7", "authRoute":"Existing stock xAI OAuth; API key env removed",
        "cwd":str(workdir),"command":args,"configSHA256":sha256(config.read_bytes()).hexdigest(),
        "probeSHA256":PROBE_SHA,"launcherSHA256":LAUNCH_SHA,"sessionId":session,
    }
    print(json.dumps({"attempt":result,"preflight":pre}), flush=True)
    before=snapshot()
    start=time.monotonic()
    with (record/"grok-headless-close.stdout.jsonl").open("wb") as stream, (record/"grok-headless-close.stderr.txt").open("wb") as errors:
        proc=subprocess.Popen(args,cwd=workdir,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=errors)
        result["clientPid"]=proc.pid
        observer = None
        trace = record / "grok-headless-close.wire.jsonl"
        try:
            deadline = start + 24
            while proc.poll() is None and time.monotonic() < deadline:
                if trace.exists():
                    first = trace.read_text(encoding="utf-8").splitlines()[:1]
                    if first:
                        event = json.loads(first[0])
                        if event["event"] == "start":
                            result["observedServerPid"] = event["pid"]
                            try:
                                observer = process_observer(event["pid"])
                            except OSError:
                                pass
                            else:
                                result["serverObservedLiveBeforeClientExit"] = not read_process(observer, 0)["exited"]
                                break
                time.sleep(0.05)
            result["exit"] = proc.wait(timeout=max(1, 65 - (time.monotonic() - start)))
        except subprocess.TimeoutExpired:
            proc.terminate()
            result["exit"] = proc.wait(timeout=10)
            result["timedOut"] = True
        finally:
            if observer is not None:
                try:
                    result["probeAfterClientExit"] = read_process(observer, 6000)
                finally:
                    observer[0].CloseHandle(observer[1])
    result["seconds"]=round(time.monotonic()-start,3)
    result["normalConfigUnchanged"]=snapshot()==before
    assert_artifact()
    trace=record/"grok-headless-close.wire.jsonl"
    result["wire"]=[json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()] if trace.is_file() else []
    (record/"grok-headless-close.result.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({key:result[key] for key in ("exit","seconds","normalConfigUnchanged","wire","probeAfterClientExit") if key in result}),flush=True)


if __name__ == "__main__":
    config_path = Path(sys.argv[1]).resolve() / "grok/.grok/config.toml"
    expected = BASE / "runs/stage-0c-zmxauqt5/grok/.grok/config.toml"
    if config_path != expected.resolve():
        raise SystemExit("Unexpected disposable configuration path")
    retained = config_path.read_bytes()
    try:
        exercise()
    finally:
        if config_path.read_bytes() != retained:
            config_path.write_bytes(retained)

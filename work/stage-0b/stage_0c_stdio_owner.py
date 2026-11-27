"""Disposable Windows stdio ownership test for the unchanged Stage 0B fixture."""

from __future__ import annotations

import _winapi
from hashlib import sha256
import json
from multiprocessing.connection import PipeClient, PipeConnection
import os
from pathlib import Path
from queue import Empty, Queue
import re
import secrets
import subprocess
import sys
from threading import Thread
import time
import uuid
from zipfile import ZipFile

BASE = Path(__file__).resolve().parent
RUN = BASE / "runs/stage-0c-zmxauqt5"
PROJECT = RUN / "grok"
CONFIG = PROJECT / ".grok/config.toml"
PROBE = "d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770"
LAUNCHER = "766a332abdd72e8233267796e2961f8b1cbc2fa9d875c656891f76bcdff32683"
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
PREFIX = "\\\\.\\pipe\\wpai-stage0c-"
MAX_CHUNK = 8192
MAX_FORWARD = 1024 * 1024
MODEL_ECHO = {"value":{"label":"WPAI","count":7,"enabled":True}}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def check_artifact():
    assert digest(BASE/"probe.py")==PROBE and digest(BASE/"launch_probe.py")==LAUNCHER
    with ZipFile(BASE.parent.parent/"outputs/stage-0b-mcp-probe.zip") as archive:
        for filename in ("probe.py","launch_probe.py"):
            assert archive.read(filename)==(BASE/filename).read_bytes()


def user_settings():
    root=Path(os.environ["USERPROFILE"])/".grok"
    return {filename:digest(root/filename) if (root/filename).is_file() else None
            for filename in ("config.toml","requirements.toml","managed_config.toml")}


def fixed_env():
    env=os.environ.copy()
    for name in ("XAI_API_KEY","GROK_API_KEY","GROK_XAI_API_BASE_URL",
                 "GROK_MODELS_BASE_URL","GROK_MODELS_LIST_URL"):
        env.pop(name,None)
    for product in ("CLAUDE","CURSOR"):
        for feature in ("SKILLS","RULES","AGENTS","MCPS","HOOKS"):
            env[f"GROK_{product}_{feature}_ENABLED"]="0"
    env["GROK_DISABLE_AUTOUPDATER"]="1"
    return env


def relay(address, capability):
    assert address.startswith(PREFIX) and len(address)==len(PREFIX)+32
    assert re.fullmatch(r"[0-9a-f]{64}",capability)
    with PipeClient(address) as channel:
        channel.send_bytes(capability.encode("ascii"))
        if not channel.poll(8) or channel.recv_bytes(32)!=b"OK":
            raise SystemExit("Local supervisor handshake failed")

        def upload():
            try:
                while data:=sys.stdin.buffer.read1(MAX_CHUNK):
                    channel.send_bytes(data)
                channel.send_bytes(b"")
            except (EOFError,OSError):
                return

        Thread(target=upload,daemon=True).start()
        try:
            while data:=channel.recv_bytes(MAX_CHUNK):
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
        except (EOFError,BrokenPipeError,OSError):
            pass


def start_owner(address, capability, label, result, threads):
    handle=_winapi.CreateNamedPipe(
        address,
        _winapi.PIPE_ACCESS_DUPLEX|_winapi.FILE_FLAG_OVERLAPPED|_winapi.FILE_FLAG_FIRST_PIPE_INSTANCE,
        _winapi.PIPE_TYPE_MESSAGE|_winapi.PIPE_READMODE_MESSAGE|PIPE_REJECT_REMOTE_CLIENTS,
        1,MAX_CHUNK,MAX_CHUNK,1000,_winapi.NULL)
    connected=False
    child=None
    try:
        ov=_winapi.ConnectNamedPipe(handle,overlapped=True)
        if _winapi.WaitForMultipleObjects([ov.event],False,16000)!=0:
            ov.cancel()
            ov.GetOverlappedResult(True)
            raise RuntimeError("No relay connected to the one-time local pipe")
        _,status=ov.GetOverlappedResult(True)
        if status:
            raise RuntimeError(f"Local pipe connection failed: {status}")
        with PipeConnection(handle) as channel:
            connected=True
            if not channel.poll(5) or not secrets.compare_digest(
                    channel.recv_bytes(128),capability.encode("ascii")):
                raise RuntimeError("Local relay capability rejected")
            child=subprocess.Popen(
                [sys.executable,"-I","-B",str(BASE/"launch_probe.py"),str(RUN),label],
                cwd=BASE,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                env={k:os.environ[k] for k in ("SystemRoot","WINDIR") if k in os.environ})
            result["launcherPid"]=child.pid
            channel.send_bytes(b"OK")

            def download():
                total=0
                try:
                    while data:=channel.recv_bytes(MAX_CHUNK):
                        total+=len(data)
                        if total>MAX_FORWARD:
                            raise RuntimeError("Input relay limit exceeded")
                        child.stdin.write(data)
                        child.stdin.flush()
                    result["disconnect"]="stdio EOF frame"
                except (EOFError,OSError):
                    result["disconnect"]="Windows peer closed"
                except (ValueError,RuntimeError) as exc:
                    result["relayInputError"]=str(exc)
                finally:
                    child.stdin.close()
                    result["closedProbeStdin"]=True

            def upload():
                total=0
                try:
                    while data:=child.stdout.read1(MAX_CHUNK):
                        total+=len(data)
                        if total>MAX_FORWARD:
                            raise RuntimeError("Output relay limit exceeded")
                        channel.send_bytes(data)
                except (OSError,EOFError,ValueError):
                    return
                except RuntimeError as exc:
                    result["relayOutputError"]=str(exc)

            for worker in (download,upload):
                thread=Thread(target=worker,daemon=True)
                threads.append(thread)
                thread.start()
            result["launcherExit"]=child.wait(timeout=65)
            # Let the output worker flush the final response before the pipe is closed.
            threads[-1].join(1)
    except Exception as exc:
        result["ownerError"]=str(exc)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            result["forcedLauncherExit"]=child.wait(timeout=5)
        if not connected:
            _winapi.CloseHandle(handle)


def wait_frame(proc):
    lines=Queue()
    thread=Thread(target=lambda:lines.put(proc.stdout.readline()),daemon=True)
    thread.start()
    try:
        return json.loads(lines.get(timeout=6))
    except Empty:
        raise RuntimeError("Control relay did not return a response") from None


def control(relay_args, result):
    with subprocess.Popen(relay_args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as client:
        try:
            client.stdin.write(b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"lifecycle-control","version":"1"}}}\n')
            client.stdin.flush()
            message=wait_frame(client)
            assert message["result"]["serverInfo"]["version"]=="0.1.1"
            assert message["result"]["protocolVersion"]=="2025-11-25"
            result["exactControlReply"]=message
        finally:
            # This simulates Grok dropping the transport. Only our own relay is terminated.
            client.terminate()
            result["simulatedRelayExit"]=client.wait(timeout=5)


def grok(relay_args, result, label):
    before=CONFIG.read_bytes()
    expected=(RUN/"grok-qualified.config.toml").read_bytes()
    assert before==expected
    primary=json.loads((RUN/"grok-qualified.result.json").read_text(encoding="utf-8-sig"))
    source_prompt=(RUN/"grok-qualified.prompt.txt").read_text(encoding="utf-8-sig")
    args=primary["command"].copy()
    assert args[args.index("--permission-mode")+1]=="dontAsk"
    assert "--always-approve" not in args and args.count("--allow")==5
    args[args.index("--session-id")+1]=str(uuid.uuid4())
    prompt=RUN/f"{label}.prompt.txt"
    prompt.write_text(source_prompt,encoding="utf-8")
    args[args.index("--prompt-file")+1]=str(prompt)
    config=re.sub(r"(?m)^command = .+$",lambda _:f"command = {json.dumps(sys.executable)}",before.decode(),count=1)
    config=re.sub(r"(?m)^args = .+$",lambda _:f"args = {json.dumps(relay_args[1:])}",config,count=1)
    # The pipe capability never appears in the retained command or report.
    result["disposableConfigSHA256"]=sha256(config.encode()).hexdigest()
    env=fixed_env()
    settings_before=user_settings()
    try:
        CONFIG.write_bytes(config.encode())
        inspect_run=subprocess.run([args[0],"--no-auto-update","inspect","--json"],
            cwd=PROJECT,env=env,capture_output=True,text=True,encoding="utf-8",timeout=10,check=True)
        inspection=json.loads(inspect_run.stdout)
        assert inspection["projectTrusted"]
        assert [(x["name"],x["transport"]) for x in inspection["mcpServers"]]==[("wpai_probe","stdio")]
        assert not inspection["hooks"] and not any(p["enabled"] for p in inspection["plugins"])
        current_version=subprocess.check_output([args[0],"--no-auto-update","--version"],text=True,env=env).strip()
        assert current_version=="grok 1.0.92 (b06756fd6256) [stable]"
        result.update(argv=args,authRoute="Existing grok.com OAuth",installedVersion=current_version)
        with (RUN/f"{label}.stdout.jsonl").open("wb") as stdout, (RUN/f"{label}.stderr.txt").open("wb") as stderr:
            process=subprocess.Popen(args,cwd=PROJECT,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
            result["grokPid"]=process.pid
            start=time.monotonic()
            try:
                result["grokExit"]=process.wait(timeout=65)
            except subprocess.TimeoutExpired:
                process.terminate()
                result["grokExit"]=process.wait(timeout=5)
                result["forcedGrokExit"]=True
            result["grokSeconds"]=round(time.monotonic()-start,3)
    finally:
        CONFIG.write_bytes(before)
        result["normalSettingsUnchanged"]=user_settings()==settings_before


def exercise(mode):
    check_artifact()
    label=f"grok-owner-{mode}"
    evidence=RUN/f"{label}.json"
    wire=RUN/f"{label}.wire.jsonl"
    if evidence.exists() or wire.exists():
        raise SystemExit("Existing evidence must be preserved")
    address=PREFIX+secrets.token_hex(16)
    capability=secrets.token_hex(32)
    args=[sys.executable,"-I","-B",str(Path(__file__).resolve()),"relay",address,capability]
    result={"mode":mode,"stage0bProbeSHA256":PROBE,"stage0bLauncherSHA256":LAUNCHER,
            "transport":"One-instance Windows local-only named pipe with one-time capability",
            "supervisorPid":os.getpid()}
    io_threads=[]
    owner=Thread(target=start_owner,args=(address,capability,label,result,io_threads),daemon=True)
    owner.start()
    # ConnectNamedPipe is armed as the owner thread starts. WaitNamedPipe is local-only.
    for _ in range(100):
        try:
            _winapi.WaitNamedPipe(address,50)
            break
        except OSError:
            time.sleep(0.02)
    else:
        raise RuntimeError("Disposable named pipe was unavailable")
    try:
        if mode=="control":
            control(args,result)
        else:
            grok(args,result,label)
    finally:
        owner.join(75)
        for thread in io_threads:
            thread.join(1)
        result["ownerThreadStopped"]=not owner.is_alive()
        result["relayThreadsStopped"]=bool(io_threads) and not any(t.is_alive() for t in io_threads)
        result["wire"]=[json.loads(line) for line in wire.read_text(encoding="utf-8").splitlines()] if wire.exists() else []
        check_artifact()
        evidence.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in result.items() if k!="argv"}),flush=True)
    assert result["ownerThreadStopped"] and result["relayThreadsStopped"]
    assert result["closedProbeStdin"] and result["launcherExit"]==0
    assert result["wire"][-1]=={"event":"stop","reason":"eof"}
    if mode=="live":
        assert result["normalSettingsUnchanged"] and result["grokExit"]==0


if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="relay":
        relay(sys.argv[2],sys.argv[3])
    elif mode in ("control","live"):
        exercise(mode)
    else:
        raise SystemExit("Expected control, live or relay")

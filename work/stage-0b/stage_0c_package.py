"""Check Stage 0C Grok evidence and preserve a bounded combined comparison record."""

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json
import subprocess
import sys

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parent.parent
RUN = BASE / "runs/stage-0c-zmxauqt5"
PENDING = BASE / "stage-0c-report.md"
ARCHIVE = WORKSPACE / "outputs/stage-0b-mcp-probe.zip"
EXPECTED = "d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770"
NAMES = {"probe_info", "probe_echo", "probe_validation", "probe_evidence_page", "probe_denied_operation"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def event_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.startswith("{")]


def main():
    meta = read(RUN / "grok-qualified.result.json")
    usage = read(RUN / "grok-qualified.usage.json")
    pre = read(RUN / "grok-qualified.preflight.json")
    assert meta["exit"] == 0 and meta["normalConfigUnchanged"]
    assert meta["probeSHA256"] == EXPECTED == sha256((BASE/"probe.py").read_bytes()).hexdigest()
    assert meta["launcherSHA256"] == sha256((BASE/"launch_probe.py").read_bytes()).hexdigest()
    actual_config = (RUN/"grok-qualified.config.toml").read_bytes()
    assert meta["configSHA256"] == sha256(actual_config).hexdigest()
    assert pre["trusted"] and pre["managedOnly"] == "off"
    assert pre["mcpServers"] == [{"name":"wpai_probe","transport":"stdio"}]
    assert not pre["enabledPlugins"] and not pre["hooks"] and pre["fixtureRuleSkips"] == 0
    assert meta["command"].count("--allow") == 5
    assert "--always-approve" not in meta["command"]

    frames = event_rows(RUN / "grok-qualified.stdout.jsonl")
    finish = next(frame for frame in frames if frame["type"] == "end")
    assert finish["stopReason"] == "end_turn"
    calls = {frame["toolCallId"]: frame for frame in frames if frame["type"] == "tool_call"}
    updates = {frame["toolCallId"]: frame for frame in frames
               if frame["type"] == "tool_call_update" and frame.get("status")}
    assert len(calls) == len(updates) == 7 and calls.keys() == updates.keys()
    results = []
    for call_id, frame in calls.items():
        raw_in = frame["rawInput"]
        final = updates[call_id]
        raw_out = final["rawOutput"]
        assert frame["toolName"] == "use_tool" and raw_out["type"] == "MCP"
        assert raw_out["server_name"] == "wpai_probe"
        tool = raw_out["tool_name"]
        assert tool in NAMES and raw_in["tool_name"] == f"wpai_probe__{tool}"
        err = raw_out.get("is_error", False)
        text = raw_out["output"]["Error" if err else "OkayOutput"]
        results.append({"clientEventId":call_id,"operation":tool,"input":raw_in["tool_input"],
                        "status":final["status"],"isError":err,"jsonText":text,"result":json.loads(text)})
    assert {result["operation"] for result in results} == NAMES
    wire_calls = [event for event in meta["wire"] if event["event"] == "call"]
    assert len(wire_calls) == 7 and {event["tool"] for event in wire_calls} == NAMES
    assert any(e["outcome"]=="DENIED" and e["protectedActions"]==0 for e in wire_calls)
    assert any(e["tool"]=="probe_validation" and e["outcome"]=="INVALID_INPUT" for e in wire_calls)
    results_by_tool = {}
    for row in results:
        results_by_tool.setdefault(row["operation"], []).append(row)
    echo = results_by_tool["probe_echo"][0]["result"]
    denial = results_by_tool["probe_denied_operation"][0]["result"]
    assert denial == {"code":"DENIED","protectedActions":0}
    assert results_by_tool["probe_validation"][0]["result"] == {"valid":True,"count":9}
    assert results_by_tool["probe_validation"][1]["result"] == {"code":"INVALID_INPUT","reason":"Expected an integer"}
    page1, page2 = results_by_tool["probe_evidence_page"]
    assert page1["result"]["rows"] == ["alder","birch"] and page1["result"]["page"] == 1
    assert page2["input"]["cursor"] == page1["result"]["nextCursor"]
    assert page2["result"] == {"page":2,"rows":["cedar","dogwood"],"nextCursor":None}
    with ZipFile(ARCHIVE) as old:
        model = json.loads(old.read("records/agy-live.json"))
        codex = json.loads(old.read("records/codex-legacy.json"))
        assert old.testzip() is None and old.read("probe.py") == (BASE/"probe.py").read_bytes()
        assert hashlib_safe(old.read("launch_probe.py")) == meta["launcherSHA256"]
        assert echo == codex["operations"]["echo"] == model["expectedEcho"]
        assert denial == codex["operations"]["denied"]
        assert page2["result"] == codex["operations"]["nextPage"]
    last_idx = max(i for i,f in enumerate(frames) if f["type"]=="tool_call_update")
    final_model_text = "".join(f.get("data","") for f in frames[last_idx+1:] if f["type"]=="text")
    assert "protectedActions" in final_model_text and "WPAI" in final_model_text
    assert usage["primaryModelId"] == "grok-4.7-build" and usage["modelCalls"] == 3
    assert usage["inputTokens"] + usage["outputTokens"] == usage["totalTokens"]
    blocked_stream = event_rows(RUN / "grok-invoke.stdout.jsonl")
    blocked = next(f for f in blocked_stream if f["type"]=="end")
    initial_error = event_rows(RUN / "grok-live.stdout.jsonl")[0]["message"]
    diag = event_rows(RUN / "grok-shutdown-check.wire.jsonl")
    assert diag[-1] == {"event":"stop","reason":"eof"}
    pids = sorted({item["pid"] for wire in [meta["wire"], diag, read(RUN/"grok-invoke.result.json")["wire"]]
                   for item in wire if item["event"]=="start"})
    check = subprocess.run([
        "pwsh", "-NoLogo", "-NoProfile", "-Command",
        "$owned=@(" + ",".join(map(str,pids)) + "); "
        "$left=@(Get-Process -Id $owned -ErrorAction SilentlyContinue | Where-Object ProcessName -eq 'python'); "
        "$listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
        "Where-Object OwningProcess -in $owned); "
        "[pscustomobject]@{liveProbePids=$left.Count;listenersAtRecordedPids=$listeners.Count}|ConvertTo-Json -Compress",
    ], check=True, capture_output=True, text=True, timeout=10)
    cleanup = json.loads(check.stdout)
    assert cleanup == {"liveProbePids":0,"listenersAtRecordedPids":0}
    payload = {
        "stage0bArchiveSHA256":sha256(ARCHIVE.read_bytes()).hexdigest(),
        "execution":meta, "preflight":pre, "clientToolResults":results,
        "finalModelText":final_model_text,
        "retention":{"jsonText":"confirmed","separateStructuredContent":"not exposed in Grok tool event"},
        "shutdown":{"agentExit":meta["exit"],"stopReason":finish["stopReason"],"headlessServerEOF":False,
                    "diagnosticWire":diag,"recordedPids":pids,**cleanup},
        "usage":usage, "quotaDelta":"unavailable",
        "priorAttempts":[{"stage":"model selection","error":initial_error,"wireCalls":0},
                         {"stage":"client dispatch","stopReason":blocked["stopReason"],
                          "reportedUsage":blocked["usage"],"wireCalls":0,
                          "errors":[
                              "Tool search was denied by the Read rule.",
                              "The short MCP name did not reach the server. The headless dispatcher reported cancellation.",
                          ]}],
        "claude":{"status":"deferred by director","localAuthStatus":{"loggedIn":False,"authMethod":"none"}}
    }
    rendered = json.dumps(payload, indent=2) + "\n"
    out = WORKSPACE / "outputs/stage-0c-grok-evidence.json"
    out.write_text(rendered,encoding="utf-8")
    reloaded = read(out)
    assert reloaded["clientToolResults"] == results
    print("evidence",hashlib_safe(out.read_bytes()),out.stat().st_size)
    print("cleanup",json.dumps(cleanup))


def hashlib_safe(data):
    return sha256(data).hexdigest()


if __name__ == "__main__":
    main()

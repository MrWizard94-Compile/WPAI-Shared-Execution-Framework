"""Offline wire and oracle checks. These direct calls are not agent evidence."""

from hashlib import sha256
import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread

from benchmark import BENCH, exact, parse, prepare, prompt, score


VERSIONS = ("2025-06-18", "2025-11-25", "2026-07-28")
META = "io.modelcontextprotocol/"


def wire(root, arm, version, expected):
    path = root / (arm + "-" + version)
    script = prepare(path, arm)
    trace = path / "trace.jsonl"
    process = subprocess.Popen([sys.executable, "-B", "-s", str(script), arm, str(trace)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=path)
    lines = Queue()

    def read():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    reader = Thread(target=read, daemon=True)
    reader.start()
    counter = 0

    def call(method, params=None, notify=False):
        nonlocal counter
        counter += 1
        out = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            out["id"] = counter
        process.stdin.write(json.dumps(out).encode("ascii") + b"\n")
        process.stdin.flush()
        if not notify:
            response = json.loads(lines.get(timeout=8))
            assert response["id"] == counter
            return response["result"]

    try:
        modern = version == VERSIONS[-1]
        envelope = {"_meta": {META + "protocolVersion": version, META + "clientCapabilities": {}}} if modern else {}
        if modern:
            assert version in call("server/discover", envelope)["supportedVersions"]
        else:
            assert call("initialize", {"protocolVersion": version, "capabilities": {},
                                       "clientInfo": {"name": "offline-verifier", "version": "1"}})["protocolVersion"] == version
            call("notifications/initialized", notify=True)
        catalog = call("tools/list", envelope)["tools"]
        name = "fixture_read_field_v1" if arm == "control" else "repo_health_v1"
        assert [row["name"] for row in catalog] == [name]
        assert "trackforge" not in json.dumps(catalog).lower()

        def tool(arguments):
            result = call("tools/call", {**envelope, "name": name, "arguments": arguments})
            payload = result["structuredContent"]
            assert json.loads(result["content"][0]["text"]) == payload
            return payload

        key = "field" if arm == "control" else "project"
        assert tool({key: "not-a-target"})["status"] == "DENIED"
        assert tool({key: "not-a-target", "path": "anywhere"})["status"] == "INVALID_ARGUMENTS"
        if arm == "control":
            heard = {k: tool({key: k})["fact"] for k in expected}
        else:
            heard = tool({key: "fictional-clockwork-museum"})["facts"]
        assert exact(heard, expected)
        process.stdin.close()
        assert process.wait(timeout=8) == 0 and process.stderr.read() == b""
        assert lines.get(timeout=4) is None
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        assert events[-1]["event"] == "stop" and not events[-1]["worker_alive"]
        assert all(e["process_attempts"] == 0 for e in events if e["event"] == "acquisition")
        assert all(e["parity"] for e in events if e["event"] == "sent" and e["method"] == "tools/call")
        return heard
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=4)
        reader.join(3)
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()


def main():
    expected = parse((BENCH / "ground_truth.json").read_bytes())
    assert len(expected["facts"]) == 12
    assert score(json.dumps(expected), expected)["passed"]
    bad = parse(json.dumps(expected))
    bad["facts"]["05_change_counts"]["value"]["staged"] = 2.0
    assert score(json.dumps(bad), expected)["fields"]["05_change_counts"] == "altered"
    bad["facts"]["03_remote_main"]["value"] = "0" * 40
    bad["facts"]["11_failed_checks"] = bad["facts"].pop("09_open_pull_requests")
    bad["facts"]["unsupported"] = {"value": "invented"}
    scored = score(json.dumps(bad), expected)
    assert not scored["passed"] and scored["extra_field_count"] == 1
    assert [scored["fields"][key] for key in ("03_remote_main", "09_open_pull_requests", "11_failed_checks")] == [
        "altered", "missing", "altered"]
    assert not score('{"schema":"x","schema":"y"}', expected)["valid_json"]
    hashes = {name: sha256((BENCH / name).read_bytes()).hexdigest() for name in
              ("ground_truth.json", "response_schema.json", "task.txt", "control.txt", "treatment.txt")}
    for arm in ("control", "treatment"):
        hashes[f"rendered_{arm}_prompt"] = sha256(prompt(arm).encode()).hexdigest()
    with TemporaryDirectory(prefix="wpai-synthetic-wire-") as fresh:
        for revision in VERSIONS:
            baseline, treatment = [wire(Path(fresh), arm, revision, expected["facts"]) for arm in ("control", "treatment")]
            assert exact(baseline, treatment)
    print(json.dumps({"revisions": VERSIONS, "arms": 2, "facts": 12, "hashes": hashes}))


if __name__ == "__main__":
    main()

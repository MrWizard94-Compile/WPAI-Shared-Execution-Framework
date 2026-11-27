import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from zipfile import ZipFile, ZIP_DEFLATED

workspace = Path.cwd()
fixture = workspace / "work/stage-0b"
runs = fixture / "runs"
out = workspace / "outputs"
source_names = ["probe.py", "launch_probe.py", "run_probe.py", "run_agy_live.py", "verify_boundaries.py"]
selection = {
    "direct-legacy": "stage-0b-ib13i55l", "direct-modern": "stage-0b-7j89w1cz",
    "codex-legacy": "stage-0b-_wbeoeq1", "codex-modern": "stage-0b-n5hicbq3",
    "sdk-legacy": "stage-0b-j50bwj7o", "grok": "stage-0b-j50bwj7o",
    "claude": "stage-0b-j50bwj7o", "claude-modern": "stage-0b-j50bwj7o",
    "gemini": "stage-0b-j50bwj7o", "agy": "stage-0b-j50bwj7o",
    "agy-live": "stage-0b-agy-live-yqszulyt",
}
artifacts = {name: (fixture / name).read_bytes() for name in ["README.md", *source_names]}
for name in source_names:
    ast.parse(artifacts[name], filename=name)
probe_sha = sha256(artifacts["probe.py"]).hexdigest()
assert probe_sha == "d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770"
assert b"twenty seconds" in artifacts["README.md"]
cases = {}


def normalize(value):
    if isinstance(value, str):
        return value.replace(str(fixture), "%PROBE_ROOT%").replace(os.environ["USERPROFILE"], "%USERPROFILE%")
    if isinstance(value, dict):
        return {key: normalize(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize(child) for child in value]
    return value


def record(name, value):
    artifacts[f"records/{name}.json"] = (json.dumps(normalize(value), indent=2) + "\n").encode("utf-8")


for case, folder in selection.items():
    result = json.loads((runs / folder / f"{case}.json").read_text(encoding="utf-8"))
    assert (result.get("serverSHA256") or result.get("probe_sha256")) == probe_sha
    assert "error" not in result and "driverError" not in result
    cases[case] = result
    record(case, result)

expected = {"value": {"label": "WPAI", "count": 7, "enabled": True}}
for name in ("codex-legacy", "codex-modern"):
    results = cases[name]["operations"]
    assert results["echo"] == expected
    assert results["denied"]["protectedActions"] == 0
    assert results["nextPage"]["rows"] == ["cedar", "dogwood"]
    assert results["expiredCursor"]["code"] == "CURSOR_EXPIRED_OR_UNKNOWN"
for name in ("direct-legacy", "direct-modern"):
    attempts = cases[name]["reconnections"]
    assert attempts[0]["operations"]["echo"] == expected
    assert attempts[0]["operations"]["expiredCursor"]["code"] == "CURSOR_EXPIRED_OR_UNKNOWN"
    assert all(run["process"] == {"exit": 0, "forced": False} for run in attempts)
for name in ("grok", "codex-legacy", "claude", "agy"):
    assert any(event["event"] == "catalog" and event["tools"] == 5 for event in cases[name]["wire"])
gem = cases["gemini"]
assert "untrusted" in gem["workspaceMcp"]["stderr"]
assert "Connected" in gem["workspaceMcpExplicitTrust"]["stderr"]
assert any(event["event"] == "ping" for event in gem["wire"])
assert not any(event["event"] == "catalog" for event in gem["wire"])

live = cases["agy-live"]
assert live["stopReason"] == "end_turn" and live["existingSettingsUnchanged"]
assert live["process"] == {"exit": 0, "forced": False}
reply = live["reply"]
fence = chr(96) * 3
echo = re.search(f"{fence}json\n({{.*}})\n{fence}", reply)
assert echo and json.loads(echo[1]) == expected
live_calls = [e for e in live["wire"] if e["event"] == "call"]
assert len({e["tool"] for e in live_calls}) == 5
assert sum(e["tool"] == "probe_evidence_page" and e["outcome"] == "OK" for e in live_calls) == 2
assert '"page":2,"rows":["cedar","dogwood"],"nextCursor":null' in reply
assert any(e["outcome"] == "DENIED" and e["protectedActions"] == 0 for e in live_calls)
assert sum(e["tool"] == "probe_validation" for e in live_calls) == 1
assert "additional properties 'extra' not allowed" in reply

record("install-and-boundaries", {
    "antigravity": {
        "version": "1.5.18", "binary": "%LOCALAPPDATA%/agy/bin/agy.exe", "publisher": "Google LLC",
        "authenticode": "Valid", "freshPowerShellVerified": True,
        "sha512": "53605db7013dfed51e8c416d51e0c17a3b5ad0750c13da5669954ba4a281318746be0cf8cde2b256cfdb4bfbdade4badad1a0503931f8458416184549afa06b6",
    },
    "gemini": {
        "version": "0.71.1", "package": "@google/gemini-cli", "directory": "%APPDATA%/npm/node_modules/@google/gemini-cli",
        "sri": "sha512-FYDTjU+9BFPYKBcFS3vCjJol8pFyV0iHVigUNr2wZqk4vYNFgacGB5ubyrySFGM5jWxCK+1EFdcDJiEQjNomaw==",
        "registrySignaturesVerified": 2, "warning": "@github/keytar@7.10.6 deprecated",
        "node": "25.6.0", "npm": "11.8.0", "freshPowerShellVerified": True,
    },
    "boundaries": ["uninitialized_call_rejected", "duplicate_json_key_rejected",
        "unsupported_protocol_rejected", "authorization_before_argument_dispatch",
        "frame_limit", "message_limit", "stdio_json_only", "exit_on_eof"],
    "liveFixtureProbeTcpListeners": 0,
    "notes": "Structured path fields are normalized where possible. Synthetic inputs, outputs and wire events are retained.",
})

manifest = [f"{sha256(data).hexdigest()}  {name}" for name, data in sorted(artifacts.items())]
artifacts["SHA256SUMS.txt"] = ("\n".join(manifest) + "\n").encode("utf-8")
archive = out / "stage-0b-mcp-probe.zip"
with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
    for name, data in artifacts.items():
        bundle.writestr(name, data)
with ZipFile(archive) as bundle:
    assert bundle.testzip() is None and set(bundle.namelist()) == set(artifacts)
    for line in bundle.read("SHA256SUMS.txt").decode("utf-8").splitlines():
        digest, name = line.split("  ", 1)
        assert sha256(bundle.read(name)).hexdigest() == digest

report = (fixture / "report.md").read_text(encoding="utf-8")
report = report.replace("Four checked existing settings files matched their pre-run state.",
                        "Existence and contents at the four checked normal settings paths matched their pre-run state.")
assert re.findall(r"^## ([A-G])\.", report, re.MULTILINE) == list("ABCDEFG")
assert probe_sha in report
output = out / "wpai-stage-0b-report.md"
output.write_text(report, encoding="utf-8", newline="\n")
for path in (output, archive):
    print(f"{sha256(path.read_bytes()).hexdigest()} {path.name} {path.stat().st_size} bytes")
print(f"verified_archive_entries={len(artifacts)}")
print("recorded_probe_pids=" + ",".join(
    str(e["pid"]) for case in cases.values() for e in case["wire"] if e["event"] == "start"
))

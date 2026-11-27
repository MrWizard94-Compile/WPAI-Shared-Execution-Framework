"""Private acceptance runner. Uses the Stage 0B process driver with a new server."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp

WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(WORK / "stage-0b"))
from run_probe import as_json, command_path, isolated_env, rpc_process


ROOT = Path("C:/WPAI/Software/TrackForge")
REPO = "MrWizard94-Compile/TrackForge"
SERVER = (Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else WORK / "wpai-exec") / "wpai_exec.py"
TOOL = "repo_health_v1"
MODERN = "2026-07-28"
REF_QUERY = "/git/ref/heads/main"
SERVER_ARGS = [sys.executable, "-B", str(SERVER), "stdio"]


def independent_git(*args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    return subprocess.check_output([command_path("git"), "-C", str(ROOT), "-c", "core.fsmonitor=false", *args],
                                   env=env, timeout=12).decode("utf-8", errors="surrogateescape")


def independent_github(suffix):
    return json.loads(subprocess.check_output([command_path("gh"), "api", "--method", "GET", "--hostname",
                                               "github.com", f"/repos/{REPO}{suffix}"], timeout=9))


def fingerprint():
    files = [ROOT / ".git" / name for name in ("HEAD", "index", "config", "packed-refs", "FETCH_HEAD")]
    files.extend(path for path in (ROOT / ".git" / "refs").rglob("*") if path.is_file())
    return {str(path.relative_to(ROOT)): [sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns]
            for path in files if path.is_file()}


def decode(reply, status):
    assert bool(reply.get("isError", False)) == (status != "OK")
    raw = reply["content"][0]["text"]
    assert len(raw.encode()) <= 96 * 1024
    result = json.loads(raw)
    assert reply["structuredContent"] == result, "text and structured result differ"
    assert result["status"] == status
    return result, len(raw.encode())


def direct(run, modern):
    case = run / ("direct-modern" if modern else "direct-legacy")
    case.mkdir()
    result = {}
    meta = {}
    with rpc_process(SERVER_ARGS, case, os.environ, case / "stderr.log", result) as rpc:
        if modern:
            meta = {"_meta": {"io.modelcontextprotocol/protocolVersion": MODERN,
                              "io.modelcontextprotocol/clientCapabilities": {}}}
            hello = rpc.call("server/discover", meta)
            assert hello["resultType"] == "complete" and MODERN in hello["supportedVersions"]
            result["protocol"] = MODERN
        else:
            hello = rpc.call("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                            "clientInfo": {"name": "wpai-verifier", "version": "1"}})
            assert hello["protocolVersion"] == "2025-11-25"
            result["protocol"] = hello["protocolVersion"]
            rpc.notify("notifications/initialized")
            assert rpc.call("ping", {}) == {}
        catalog = rpc.call("tools/list", meta)["tools"]
        assert [tool["name"] for tool in catalog] == [TOOL]
        result["catalog"] = [tool["name"] for tool in catalog]
        invoke = lambda project: rpc.call("tools/call", {
            **meta, "name": TOOL, "arguments": {"project": project},
        }, timeout=28)
        result["denial"] = decode(invoke("denied-project"), "DENIED")[0]
        reply = invoke("trackforge")
        assert (reply.get("resultType") == "complete") == modern
        result["health"], result["bytes"] = decode(reply, "OK")
    assert result["process"] == {"exit": 0, "forced": False}
    return result


def codex(run, modern):
    case = run / ("codex-modern" if modern else "codex-legacy")
    env = isolated_env(case)
    config = Path(env["CODEX_HOME"]) / "config.toml"
    config.parent.mkdir()
    pin = ("[features]\nmcp_2026_07_28 = true\n" if modern else "")
    profile = ('[mcp_servers.wpai_exec.env]\nCODEX_MCP_PROTOCOL_VERSION = "2026-07-28"\n' if modern else "")
    config.write_text('approval_policy = "never"\nsandbox_mode = "read-only"\n'
                      f'{pin}[mcp_servers.wpai_exec]\ncommand = {json.dumps(SERVER_ARGS[0])}\n'
                      f'args = {json.dumps(SERVER_ARGS[1:])}\nrequired = true\n'
                      f'startup_timeout_sec = 10\ntool_timeout_sec = 28\n{profile}', encoding="utf-8")
    result = {}
    argv = [command_path("codex.exe"), "app-server", "--listen", "stdio://"]
    with rpc_process(argv, case, env, case / "stderr.log", result) as rpc:
        rpc.call("initialize", {"clientInfo": {"name": "wpai-stage-1", "title": "WPAI Stage 1", "version": "1"},
                                "capabilities": {"experimentalApi": True, "requestAttestation": False}})
        rpc.notify("initialized")
        listing = rpc.call("mcpServerStatus/list", {})
        item = next(row for row in listing["data"] if row["name"] == "wpai_exec")
        assert set(item["tools"]) == {TOOL}
        result["catalog"] = sorted(item["tools"])
        thread = rpc.call("thread/start", {"cwd": str(case), "ephemeral": True})["thread"]["id"]

        def invoke(project):
            return rpc.call("mcpServer/tool/call", {"threadId": thread, "server": "wpai_exec", "tool": TOOL,
                                                    "arguments": {"project": project}}, timeout=30)

        result["denial"] = decode(invoke("denied-project"), "DENIED")[0]
        result["health"], result["bytes"] = decode(invoke("trackforge"), "OK")
        # The app-server control carries no GitHub or provider credentials and has a dead proxy.
        assert result["health"]["facts"]["03_remote_main"]["status"] == "unavailable"
        assert result["health"]["facts"]["02_local_head"]["status"] == "observed"
    assert result["process"] == {"exit": 0, "forced": False}
    return result


def independent_comparison(payload):
    values = {key: fact["value"] for key, fact in payload["facts"].items()}
    local_sha, local_branch = independent_git("rev-parse", "HEAD", "--abbrev-ref", "HEAD").splitlines()
    ls_remote = dict((row.split()[1], row.split()[0]) for row in independent_git(
        "ls-remote", "--heads", "origin").splitlines())
    main = ls_remote["refs/heads/main"]
    queries = ["", REF_QUERY, "/pulls?state=open&per_page=11", "/actions/workflows",
               "/actions/runs?branch=main", f"/actions/runs?branch={local_branch}",
               f"/commits/{main}/check-runs", f"/commits/{main}/status", f"/commits?sha={main}&per_page=5"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        identity, live_ref, prs, workflows, main_runs, active_runs, checks, statuses, commits = list(
            pool.map(independent_github, queries))
    staged = independent_git("diff", "--no-ext-diff", "--no-textconv", "--cached", "--name-only", "-z")
    unstaged = independent_git("diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z")
    untracked = independent_git("ls-files", "--others", "--exclude-standard", "-z")
    counts = {"staged": staged.count("\0"), "unstaged": unstaged.count("\0"),
              "untracked": untracked.count("\0"), "conflicted": 0}
    # show-ref reports the original object and reference with independent formatting.
    refs = {ref: sha for sha, ref in map(str.split, independent_git("show-ref").splitlines())
            if ref.startswith(("refs/heads/", "refs/remotes/"))}
    local_main = refs["refs/heads/main"]
    divergence = {}
    for name, sha in (("local_main_divergence", local_main), ("active_divergence", local_sha)):
        behind, ahead = map(int, independent_git("rev-list", "--left-right", "--count", f"{main}...{sha}").split())
        divergence[name] = (ahead, behind)
    ci = values["10_applicable_actions"]
    ci_sources = {"workflows": workflows, "runs_main": main_runs, "runs_active": active_runs,
                  "checks_main": checks, "statuses_main": statuses}
    assert all(item["total_count"] == 0 for item in ci_sources.values()), "broaden oracle for live nonempty CI"
    local_log = independent_git("log", "--no-show-signature", "-5", "--format=%H").splitlines()
    expected_discrepancies = []
    if local_sha != main:
        expected_discrepancies.append({"type": "active_head_differs_from_live_main", "branch": local_branch})
    if any(counts.values()):
        expected_discrepancies.append({"type": "local_worktree_has_changes", "counts": counts})
    for ref, sha in sorted(refs.items()):
        if ref.startswith("refs/heads/"):
            classification, branch = "local_branch", ref.removeprefix("refs/heads/")
        elif ref.startswith("refs/remotes/origin/") and not ref.endswith("/HEAD"):
            classification, branch = "cached_origin", ref.removeprefix("refs/remotes/origin/")
        else:
            continue
        live = ls_remote.get(f"refs/heads/{branch}")
        if not live:
            expected_discrepancies.append({"type": f"{classification}_has_no_live_branch", "branch": branch})
        elif live != sha:
            expected_discrepancies.append({"type": f"{classification}_tip_differs", "branch": branch,
                                           "local_sha": sha, "live_sha": live})
    expected_discrepancies.extend({"type": "live_branch_has_no_local_branch", "branch": ref.removeprefix("refs/heads/")}
                                  for ref in sorted(ls_remote) if ref not in refs)
    tests = {
        "01_identity": values["01_identity"]["remote"]["value"]["id"] == identity["id"] == 1351477573
                       and values["01_identity"]["remote"]["value"]["full_name"] == identity["full_name"]
                       and independent_git("remote", "get-url", "origin").strip() == f"https://github.com/{REPO}.git",
        "02_local_head": values["02_local_head"] == {"branch": local_branch, "sha": local_sha},
        "03_remote_main": values["03_remote_main"] == main == live_ref["object"]["sha"],
        "04_working_tree": values["04_working_tree"] == ("dirty" if any(counts.values()) else "clean"),
        "05_change_counts": values["05_change_counts"] == counts,
        "06_branch_inventory": {row["name"]: row["sha"] for row in values["06_branch_inventory"]["local_and_cached"]["value"]["items"]} == refs
                               and {f"refs/heads/{row['name']}": row["sha"] for row in values["06_branch_inventory"]["remote_live"]["value"]["items"]} == ls_remote,
        "07_main_divergence": all((values["07_main_divergence"][key]["value"]["ahead"],
                                   values["07_main_divergence"][key]["value"]["behind"]) == expected
                                  for key, expected in divergence.items()),
        "08_recent_commits": [item["sha"] for item in values["08_recent_commits"]["local_head"]["value"]] == local_log
                             and [item["sha"] for item in values["08_recent_commits"]["remote_main"]["value"]] == [item["sha"] for item in commits],
        "09_open_pull_requests": [(row["number"], row["destination"]) for row in values["09_open_pull_requests"]["items"]]
                                 == [(row["number"], row["base"]["ref"]) for row in prs[:10]],
        "10_applicable_actions": all(ci[name]["value"]["total"] == item["total_count"] for name, item in ci_sources.items()),
        "11_failed_checks": values["11_failed_checks"] == {"items": [], "incomplete": []},
        "12_discrepancies": values["12_discrepancies"]["items"] == expected_discrepancies,
    }
    assert all(tests.values()), tests
    return {"matches": tests, "git_remote": "ls-remote --heads origin", "main_sha": main}


def main():
    run = Path(mkdtemp(prefix="stage1-verify-", dir=WORK))
    before = fingerprint()
    results = {}
    for name, callback in (("direct_legacy", lambda: direct(run, False)),
                           ("direct_modern", lambda: direct(run, True))):
        results[name] = callback()
        as_json(run / "routes.json", results)
    routes = [results[name]["health"] for name in ("direct_legacy", "direct_modern")]
    for key in ("02_local_head", "03_remote_main"):
        assert routes[0]["facts"][key]["value"] == routes[1]["facts"][key]["value"]
    oracle = independent_comparison(routes[1])
    for name, modern in (("codex_legacy", False), ("codex_modern", True)):
        results[name] = codex(run, modern)
        as_json(run / "routes.json", results)
    after = fingerprint()
    assert before == after, "Git metadata changed during observation window"
    as_json(run / "comparison.json", {"oracle": oracle, "git_metadata_unchanged": True,
                                      "git_metadata_fingerprinted": len(before),
                                      "as_of": datetime.now().astimezone().isoformat(),
                                      "server_sha256": sha256(SERVER.read_bytes()).hexdigest()})
    print(run)


if __name__ == "__main__":
    main()

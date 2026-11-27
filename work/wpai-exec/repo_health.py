"""The bounded, read-only W1 repository health operation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import quote, urlencode


CONTRACT = "wpai.repo_health.v1"
PROJECT = "trackforge"
CHECKOUT = Path("C:/WPAI/Software/TrackForge")
REPO = "MrWizard94-Compile/TrackForge"
REPO_ID = 1351477573
REF_LIMIT = 32
PAGE = 10
MAX_CAPTURE = 512 * 1024
COMMAND_SECONDS = 4
OPERATION_SECONDS = 24
FAILURES = {"failure", "timed_out", "startup_failure", "action_required", "cancelled", "stale"}
DIRECT_CAUSES = {"timed_out", "startup_failure", "action_required", "cancelled", "stale"}
SHA = re.compile(r"[a-f0-9]{40}\Z")
TERMINAL_SEQUENCE = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]|"
                               r"(?:\x1b\]|\x9d)[^\x07\x1b\x9c]*(?:\x07|\x1b\\|\x9c|$)")
LINE_SPACING = str.maketrans({char: " " for char in "\t\r\n\u2028\u2029"})


class Unavailable(Exception):
    """A bounded acquisition failed with a shareable reason."""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def compact(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def display_text(value):
    value = TERMINAL_SEQUENCE.sub("", value).translate(LINE_SPACING)
    return "".join(char for char in value if char.isprintable())


def display_facts(value):
    # Keep real identifiers for comparisons and GitHub lookups. Normalize only the report projection.
    if isinstance(value, dict):
        return {key: display_facts(item) for key, item in value.items()}
    if isinstance(value, list):
        return [display_facts(item) for item in value]
    if isinstance(value, str):
        return display_text(value)
    return value


def checked_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise Unavailable("invalid_sha")
    return value


def git_environment():
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("GIT_") and key.upper() not in {"GH_TOKEN", "GITHUB_TOKEN"}}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1",
               GIT_NO_REPLACE_OBJECTS="1", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               LC_ALL="C")
    return env


class Reader:
    def __init__(self, cancellation=None):
        self.started = time.monotonic()
        self.deadline = self.started + OPERATION_SECONDS
        self.cancellation = cancellation or threading.Event()
        self.events = []
        self.lock = threading.Lock()
        self.git_exe = shutil.which("git")
        self.gh_exe = shutil.which("gh")

    def run(self, executable, arguments, cwd, env, kind, *, empty_code=None, input_bytes=None):
        if not executable or not Path(executable).is_absolute():
            raise Unavailable(f"{kind}_unavailable")
        start = time.monotonic()
        timeout = min(COMMAND_SECONDS, self.deadline - start)
        if self.cancellation.is_set():
            raise Unavailable("request_cancelled")
        if timeout <= 0:
            raise Unavailable("operation_deadline")
        with self.lock:
            self.events.append(kind)
        try:
            process = subprocess.Popen([executable, *arguments], cwd=cwd, env=env,
                                       stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise Unavailable(f"{kind}_launch_error") from exc
        data = bytearray()
        problems = []

        def drain():
            try:
                while chunk := process.stdout.read1(16 * 1024):
                    if len(data) + len(chunk) > MAX_CAPTURE:
                        problems.append("capture_limit")
                        process.kill()
                        return
                    data.extend(chunk)
            except OSError:
                problems.append("capture_error")

        output = threading.Thread(target=drain, daemon=True)
        output.start()
        writer = None
        if input_bytes is not None:
            def supply():
                try:
                    with process.stdin:
                        process.stdin.write(input_bytes)
                except OSError:
                    problems.append("input_pipe_error")

            writer = threading.Thread(target=supply, daemon=True)
            writer.start()
        try:
            while process.poll() is None:
                delay = start + timeout - time.monotonic()
                if delay <= 0:
                    raise Unavailable(f"{kind}_timeout")
                if self.cancellation.wait(min(delay, 0.025)):
                    raise Unavailable("request_cancelled")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            output.join()
            if writer:
                writer.join()
            process.stdout.close()
        if problems:
            raise Unavailable(problems[0])
        if empty_code is not None and process.returncode == empty_code and not data:
            return b""
        if process.returncode:
            raise Unavailable(f"{kind}_exit_{process.returncode}")
        return bytes(data)

    def git(self, *args, config=(), empty_code=None, input_bytes=None):
        return self.run(self.git_exe, ["--no-pager", "-c", "core.fsmonitor=false", *config,
                                      *args], CHECKOUT, git_environment(), "git",
                        empty_code=empty_code, input_bytes=input_bytes)

    def github(self, endpoint, *, query=None, jq):
        url = f"/repos/{REPO}{endpoint}"
        if query:
            url = f"{url}?{urlencode(query)}"
        env = dict(os.environ, GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1",
                   GH_NO_EXTENSION_UPDATE_NOTIFIER="1", GH_PAGER="", NO_COLOR="1")
        env.pop("GH_DEBUG", None)
        data = self.run(self.gh_exe, ["api", "--hostname", "github.com", "--method", "GET",
                                    "--jq", jq, url], Path(__file__).resolve().parent, env, "github_get")
        return json.loads(data)


def fact(source, target, value=None, *, reason=None, status=None):
    if status is None:
        status = "unavailable" if reason else "observed"
    result = {"status": status, "source": source, "target": target, "observed_at": utc_now()}
    if status != "unavailable":
        result["value"] = value
    if reason:
        result["reason"] = reason
    return result


def observe(source, target, collect):
    try:
        value = collect()
        return fact(source, target, value, status="partial" if isinstance(value, dict) and value.get("truncated") else None)
    except Unavailable as exc:
        return fact(source, target, reason=str(exc))
    except (KeyError, TypeError, IndexError, ValueError, UnicodeError):
        return fact(source, target, reason="unexpected_source_response")


def batch(tasks):
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = {name: pool.submit(observe, *task) for name, task in tasks.items()}
        return {name: job.result() for name, job in pending.items()}


def decoded(command):
    return command.decode("utf-8", errors="surrogateescape")


def local_identity(reader):
    if not CHECKOUT.is_dir():
        raise Unavailable("checkout_missing")
    root = CHECKOUT.resolve()
    if root != CHECKOUT.absolute():
        raise Unavailable("checkout_relocated")
    paths = decoded(reader.git("rev-parse", "--show-toplevel", "--absolute-git-dir",
                               "--path-format=absolute", "--git-common-dir")).splitlines()
    if len(paths) != 3 or Path(paths[0]).resolve() != root or any(
            not Path(path).resolve().is_relative_to(root) for path in paths[1:]):
        raise Unavailable("checkout_identity_mismatch")
    origins = decoded(reader.git("config", "--local", "--no-includes", "--get-all",
                                 "remote.origin.url", empty_code=1)).splitlines()
    allowed = {f"https://github.com/{REPO}", f"git@github.com:{REPO}",
               f"ssh://git@github.com/{REPO}"}
    if len(origins) != 1 or origins[0].removesuffix(".git").lower() not in {url.lower() for url in allowed}:
        raise Unavailable("checkout_origin_mismatch")
    return {"origin_repo": REPO}


def remote_identity(reader):
    value = reader.github("", jq="{id, full_name, default_branch, private}")
    if value["id"] != REPO_ID or value["full_name"].lower() != REPO.lower() or value["private"] is not True:
        raise Unavailable("remote_repository_identity_mismatch")
    return value


def local_head(reader):
    sha = checked_sha(decoded(reader.git("rev-parse", "--verify", "HEAD")).strip())
    branch = decoded(reader.git("symbolic-ref", "--quiet", "--short", "HEAD", empty_code=1)).rstrip("\r\n")
    return {"branch": branch or None, "sha": sha}


def count_status(raw):
    counts = {"staged": 0, "unstaged": 0, "untracked": 0, "conflicted": 0}
    records = iter(raw.split(b"\0"))
    for record in records:
        if not record:
            continue
        tag = record[:2]
        if tag in (b"1 ", b"2 ", b"u ") and len(record) > 4:
            counts["staged"] += record[2:3] != b"."
            counts["unstaged"] += record[3:4] != b"."
            counts["conflicted"] += tag == b"u "
            if tag == b"2 " and not next(records, b""):
                raise Unavailable("unexpected_status_record")
        elif tag == b"? ":
            counts["untracked"] += 1
        else:
            raise Unavailable("unexpected_status_record")
    return counts


def worktree(reader):
    tracked = reader.git("ls-files", "--cached", "--stage", "-z")
    if any(entry.startswith(b"160000 ") for entry in tracked.split(b"\0")):
        raise Unavailable("submodule_worktree_not_inspected")
    # Probe attributes with Git's indexed paths. No paths or file content leave the operation.
    paths = {entry.split(b"\t", 1)[1]: None for entry in tracked.split(b"\0") if entry}
    settings = decoded(reader.git("config", "--name-only", "--get-regexp",
                                  r"^filter\..*\.(clean|process|required)$", empty_code=1))
    filters = {name.rsplit(".", 1)[0] for name in settings.splitlines()}
    if any(not re.fullmatch(r"filter\.[A-Za-z0-9_.-]+", name) for name in filters):
        raise Unavailable("unexpected_filter_configuration")
    overrides = [item for name in sorted(filters)
                 for setting in ("clean=", "process=", "required=false")
                 for item in ("-c", f"{name}.{setting}")]
    if paths:
        attr_data = reader.git("check-attr", "-z", "--stdin", "filter", input_bytes=b"\0".join(paths) + b"\0")
        attrs = attr_data.split(b"\0")
        if len(attrs) != len(paths) * 3 + 1 or any(value not in (b"unspecified", b"unset")
                                                     for value in attrs[2::3]):
            raise Unavailable("configured_clean_filter_not_executed")
    raw = reader.git("status", "--porcelain=v2", "-z", "--untracked-files=all", "--ignore-submodules=all",
                     config=overrides)
    return count_status(raw)


def local_inventory(reader):
    data = reader.git("for-each-ref", f"--count={REF_LIMIT + 1}", "--sort=refname",
                      "--format=%(refname)%09%(objectname)%09%(symref)", "refs/heads", "refs/remotes")
    refs = []
    for row in decoded(data).rstrip("\r\n").split("\n") if data else ():
        name, sha, symref = row.split("\t")
        refs.append({"name": name, "sha": checked_sha(sha), "symbolic_target": symref or None})
    return {"items": refs[:REF_LIMIT], "truncated": len(refs) > REF_LIMIT}


def remote_inventory(reader):
    rows = reader.github("/branches", query={"per_page": REF_LIMIT + 1},
                         jq="map({name, sha: .commit.sha})")
    for row in rows:
        checked_sha(row["sha"])
    return {"items": rows[:REF_LIMIT], "truncated": len(rows) > REF_LIMIT}


def remote_ref(reader, name):
    return checked_sha(reader.github(f"/git/ref/heads/{quote(name, safe='')}", jq=".object.sha | tojson"))


def divergence(reader, local, remote):
    checked_sha(local)
    checked_sha(remote)
    if local == remote:
        return {"ahead": 0, "behind": 0, "method": "equal_shas"}
    if reader.git("rev-parse", "--is-shallow-repository").strip() != b"true":
        try:
            counts = reader.git("rev-list", "--left-right", "--count", f"{remote}...{local}")
            behind, ahead = map(int, counts.split())
            return {"ahead": ahead, "behind": behind, "method": "local_object_graph"}
        except Unavailable:
            pass
    result = reader.github(f"/compare/{remote}...{local}", query={"per_page": 1},
                           jq="{ahead: .ahead_by, behind: .behind_by}")
    return {**result, "method": "github_compare"}


def local_commits(reader, sha):
    rows = decoded(reader.git("log", "-5", "--no-show-signature", "--format=%H%x09%cI%x09%s", sha, "--"))
    commits = []
    for row in rows.rstrip("\r\n").split("\n") if rows else ():
        commit, date, subject = row.split("\t", 2)
        commits.append({"sha": checked_sha(commit), "date": date, "subject": display_text(subject)[:112]})
    return commits


def remote_commits(reader, sha):
    rows = reader.github("/commits", query={"sha": sha, "per_page": 5},
                         jq='map({sha, date: .commit.committer.date, subject: (.commit.message | split("\n")[0])})')
    return [{"sha": checked_sha(row["sha"]), "date": row["date"],
             "subject": display_text(row["subject"])[:112] if isinstance(row["subject"], str) else None} for row in rows]


def pulls(reader):
    rows = reader.github("/pulls", query={"state": "open", "per_page": PAGE + 1},
                         jq="map({number, draft, destination: .base.ref, head_sha: .head.sha})")
    return {"items": rows[:PAGE], "truncated": len(rows) > PAGE}


def collection(reader, endpoint, key, fields, **query):
    response = reader.github(endpoint, query={"per_page": PAGE + 1, **query},
                             jq=f"{{total: .total_count, items: (.{key} | map({fields}))}}")
    items = response["items"]
    return {"items": items[:PAGE], "total": response["total"],
            "truncated": max(response["total"], len(items)) > PAGE}


def workflows(reader):
    return collection(reader, "/actions/workflows", "workflows", "{id, name: (.name | .[0:96]), state}")


def runs(reader, branch):
    return collection(reader, "/actions/runs", "workflow_runs",
                      "{id, name: (.name | .[0:96]), head_sha, status, conclusion, event, created_at}",
                      branch=branch)


def checks(reader, sha):
    return collection(reader, f"/commits/{sha}/check-runs", "check_runs",
                      "{id, name: (.name | .[0:96]), status, conclusion}", filter="latest")


def statuses(reader, sha):
    rows = reader.github(f"/commits/{sha}/status", query={"per_page": PAGE + 1},
                         jq="{total: .total_count, items: (.statuses | map({context: (.context | .[0:96]), state}))}")
    return {"items": rows["items"][:PAGE], "total": rows["total"],
            "truncated": max(rows["total"], len(rows["items"])) > PAGE}


def jobs(reader, run_id):
    return collection(reader, f"/actions/runs/{int(run_id)}/jobs", "jobs",
                      '{id, conclusion, name: (.name | .[0:96]), failed_steps: '
                      '([.steps[]? | select(.conclusion != "success" and .conclusion != "skipped") '
                      '| {number, name: (.name | .[0:96]), conclusion}] | .[0:5])}')


def annotate_failure(item, evidence):
    reason = item.get("conclusion", item.get("state"))
    detail = {"status": "unavailable", "reason": "provider_did_not_establish_root_cause"}
    if reason in DIRECT_CAUSES:
        detail = {"status": "observed", "provider_conclusion": reason}
    return {"evidence": evidence, "item": item, "cause": detail}


def failed_results(reader, applicable):
    failures = []
    incomplete = []
    job_tasks = {}
    targets = list(applicable)
    for name, record in applicable.items():
        value = record.get("value")
        if value is None or value["truncated"]:
            incomplete.append(name)
        if value is None:
            continue
        for item in value["items"]:
            state = item.get("conclusion", item.get("state"))
            if state not in FAILURES and state != "error":
                continue
            failures.append(annotate_failure(item, name))
            if name.startswith("runs_") and item["id"] not in job_tasks and len(job_tasks) < 3:
                run_id = item["id"]
                job_tasks[run_id] = ("github_actions_jobs", run_id, lambda rid=run_id: jobs(reader, rid))
            elif name.startswith("runs_") and item["id"] not in job_tasks:
                incomplete.append(f"jobs:{item['id']}")
    findings = batch(job_tasks)
    for failure in failures:
        evidence = failure["evidence"]
        if evidence.startswith("runs_"):
            scopes = findings.get(failure["item"]["id"])
            if scopes:
                failure["job_evidence"] = scopes
                if scopes["status"] != "observed" or scopes["value"]["truncated"]:
                    incomplete.append(f"jobs:{scopes['target']}")
    if not any("value" in record for record in applicable.values()):
        return fact("github_ci", targets, reason="applicable_ci_unavailable")
    if len(failures) > 12:
        incomplete.append("failure_detail_limit")
    return fact("github_ci", targets, {"items": failures[:12], "incomplete": sorted(set(incomplete))},
                status="partial" if incomplete else "observed")


def unavailable(source, target, prerequisite):
    return fact(source, target, reason=f"{prerequisite}_unavailable")


def combined(source, target, parts):
    observed = sum(part["status"] == "observed" for part in parts.values())
    if not any("value" in part for part in parts.values()):
        return fact(source, target, reason="no_sources_available", status="partial" if parts else "unavailable",
                    value=parts)
    return fact(source, target, parts, status="observed" if observed == len(parts) else "partial")


def discrepancies(head, main, local_refs, live_refs, working):
    result = []
    compared = []
    if head and main:
        compared.append("active_head_vs_live_main")
        if head["sha"] != main:
            result.append({"type": "active_head_differs_from_live_main", "branch": head["branch"]})
    if working is not None:
        compared.append("worktree_vs_index_and_head")
        if any(working.values()):
            result.append({"type": "local_worktree_has_changes", "counts": working})
    if local_refs is not None and live_refs is not None:
        compared.append("local_refs_vs_live_branches")
        live = {item["name"]: item["sha"] for item in live_refs["items"]}
        if main:
            live["main"] = main
        for ref in local_refs["items"]:
            name = ref["name"]
            if ref["symbolic_target"]:
                continue
            for prefix, classification in (("refs/remotes/origin/", "cached_origin"),
                                           ("refs/heads/", "local_branch")):
                if name.startswith(prefix):
                    branch = name.removeprefix(prefix)
                    current = live.get(branch)
                    if current and current != ref["sha"]:
                        result.append({"type": f"{classification}_tip_differs", "branch": branch,
                                       "local_sha": ref["sha"], "live_sha": current})
                    elif not current and not live_refs["truncated"]:
                        result.append({"type": f"{classification}_has_no_live_branch", "branch": branch})
        local_heads = {item["name"].removeprefix("refs/heads/") for item in local_refs["items"]
                       if item["name"].startswith("refs/heads/")}
        if not local_refs["truncated"]:
            result.extend({"type": "live_branch_has_no_local_branch", "branch": branch}
                          for branch in live if branch not in local_heads)
        if local_refs["truncated"] or live_refs["truncated"]:
            compared.remove("local_refs_vs_live_branches")
            compared.append("bounded_ref_samples")
        listed_main = next((item["sha"] for item in live_refs["items"] if item["name"] == "main"), None)
        if listed_main and main and listed_main != main:
            result.append({"type": "live_main_changed_between_reads", "listed_sha": listed_main,
                           "direct_sha": main})
    status = "observed" if len(compared) == 3 and "bounded_ref_samples" not in compared else "partial"
    if not compared:
        return fact("git_and_github_cross_check", REPO, reason="comparison_inputs_unavailable")
    return fact("git_and_github_cross_check", REPO,
                {"checks": compared, "items": result[:32], "truncated": len(result) > 32},
                status="partial" if len(result) > 32 else status)


def health(arguments, cancellation=None):
    # Requests cannot choose directories, repositories, executables, refs, or API paths.
    if (not isinstance(arguments, dict) or set(arguments) != {"project"}
            or not isinstance(arguments["project"], str)):
        return {"contract": CONTRACT, "status": "INVALID_ARGUMENTS"}
    if arguments["project"] != PROJECT:
        return {"contract": CONTRACT, "status": "DENIED"}

    opened_at = utc_now()
    reader = Reader(cancellation)
    identity = batch({"local": ("git_origin", PROJECT, lambda: local_identity(reader)),
                      "remote": ("github_repository", REPO, lambda: remote_identity(reader))})
    base_tasks = {
        "head": ("git_head", PROJECT, lambda: local_head(reader)),
        "working": ("git_status_porcelain_v2", PROJECT, lambda: worktree(reader)),
        "local_refs": ("git_local_and_cached_remote_refs", PROJECT, lambda: local_inventory(reader)),
        "local_main": ("git_local_ref", "refs/heads/main", lambda: checked_sha(decoded(
            reader.git("rev-parse", "--verify", "refs/heads/main")).strip())),
        "remote_main": ("github_live_ref", "refs/heads/main", lambda: remote_ref(reader, "main")),
        "live_refs": ("github_live_branches", REPO, lambda: remote_inventory(reader)),
        "pulls": ("github_open_pulls", REPO, lambda: pulls(reader)),
        "workflows": ("github_actions_workflows", REPO, lambda: workflows(reader)),
        "runs_main": ("github_actions_runs", "main", lambda: runs(reader, "main")),
    }
    local_names = {"head", "working", "local_refs", "local_main"}
    prereq = {name: "local" if name in local_names else "remote" for name in base_tasks}
    base = batch({name: task for name, task in base_tasks.items() if "value" in identity[prereq[name]]})
    for name, (source, target, _) in base_tasks.items():
        if name not in base:
            base[name] = unavailable(source, target, f"{prereq[name]}_identity")

    head = base["head"].get("value")
    main = base["remote_main"].get("value")
    local_main = base["local_main"].get("value")
    working = base["working"].get("value")
    live_refs = base["live_refs"].get("value")
    other = {}
    if head:
        other["local_commits"] = ("git_log", head["sha"], lambda: local_commits(reader, head["sha"]))
    if main:
        other["remote_commits"] = ("github_commits", main, lambda: remote_commits(reader, main))
        other["checks_main"] = ("github_check_runs", main, lambda: checks(reader, main))
        other["statuses_main"] = ("github_commit_statuses", main, lambda: statuses(reader, main))
        if local_main:
            other["local_main_divergence"] = ("git_or_github_commit_graph", [local_main, main],
                                              lambda: divergence(reader, local_main, main))
        if head and head["sha"] != local_main:
            other["active_divergence"] = ("git_or_github_commit_graph", [head["sha"], main],
                                           lambda: divergence(reader, head["sha"], main))
    if head and head["branch"] and head["branch"] != "main" and "value" in identity["remote"]:
        branch = head["branch"]
        other["runs_active"] = ("github_actions_runs", branch, lambda: runs(reader, branch))
        # Branch inventory is a sample. Resolve a missing active head directly when the sample is incomplete.
        if live_refs is None or live_refs["truncated"]:
            other["remote_active"] = ("github_live_ref", branch, lambda: remote_ref(reader, branch))
    extra = batch(other)
    if "runs_active" in extra:
        active = next((row["sha"] for row in (live_refs or {}).get("items", []) if row["name"] == branch), None)
        active = extra.get("remote_active", {}).get("value", active)
        if active and active != main:
            extra.update(batch({"checks_active": ("github_check_runs", active, lambda: checks(reader, active)),
                                "statuses_active": ("github_commit_statuses", active,
                                                    lambda: statuses(reader, active))}))
        elif "remote_active" in extra and not active:
            extra["checks_active"] = unavailable("github_check_runs", branch, "active_remote_sha")
            extra["statuses_active"] = unavailable("github_commit_statuses", branch, "active_remote_sha")
    compare = {key: extra.get(key, unavailable("git_or_github_commit_graph", REPO, "required_sha"))
               for key in ("local_main_divergence", "active_divergence")}
    if main and head and head["sha"] == local_main:
        compare["active_divergence"] = compare["local_main_divergence"]
    ci = {"runs_main": base["runs_main"],
          "checks_main": extra.get("checks_main", unavailable("github_check_runs", "main", "remote_main")),
          "statuses_main": extra.get("statuses_main", unavailable("github_commit_statuses", "main", "remote_main"))}
    ci.update({key: extra[key] for key in ("runs_active", "checks_active", "statuses_active") if key in extra})

    facts = {
        "01_identity": combined("git_origin_and_github_repository", REPO, identity),
        "02_local_head": base["head"],
        "03_remote_main": base["remote_main"],
        "04_working_tree": fact("git_status_porcelain_v2", PROJECT, "dirty" if any(working.values()) else "clean")
                          if working is not None else base["working"],
        "05_change_counts": base["working"],
        "06_branch_inventory": combined("git_local_cache_and_github_live_branches", REPO,
                                        {"local_and_cached": base["local_refs"], "remote_live": base["live_refs"]}),
        "07_main_divergence": combined("commit_graph", REPO, compare),
        "08_recent_commits": combined("git_and_github_commits", REPO,
                                     {"local_head": extra.get("local_commits", unavailable("git_log", PROJECT, "head")),
                                      "remote_main": extra.get("remote_commits", unavailable(
                                          "github_commits", "main", "remote_main"))}),
        "09_open_pull_requests": base["pulls"],
        "10_applicable_actions": combined("github_actions_checks_and_statuses", REPO,
                                          {"workflows": base["workflows"], **ci}),
        "11_failed_checks": failed_results(reader, ci),
        "12_discrepancies": discrepancies(head, main, base["local_refs"].get("value"), live_refs, working),
    }
    return {"contract": CONTRACT, "status": "OK", "project": PROJECT, "opened_at": opened_at,
            "closed_at": utc_now(), "facts": display_facts(facts),
            "measurements": {"elapsed_ms": round((time.monotonic() - reader.started) * 1000, 1),
                             "git_process_attempts": reader.events.count("git"),
                             "github_get_process_attempts": reader.events.count("github_get"),
                             "provider_usage": "unavailable"}}

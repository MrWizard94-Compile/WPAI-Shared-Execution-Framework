from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

base = Path.cwd() / "work/stage-0b"
if hashlib.sha256((base/"probe.py").read_bytes()).hexdigest() != "d0e4a3e01218720002ebbf5d668972634c9f5726f8dec04f353eae4023357770":
    raise SystemExit("Stage 0B artifact hash mismatch")
if hashlib.sha256((base/"launch_probe.py").read_bytes()).hexdigest() != "766a332abdd72e8233267796e2961f8b1cbc2fa9d875c656891f76bcdff32683":
    raise SystemExit("Stage 0B launcher hash mismatch")
run = Path(tempfile.mkdtemp(prefix="stage-0c-", dir=base/"runs"))
for client in ("grok", "claude"):
    wc=run/client
    wc.mkdir()
    entry={"command": sys.executable, "args":["-I","-B",str(base/"launch_probe.py"),str(run),client]}
    if client=="grok":
        config=wc/".grok"
        config.mkdir()
        names=["probe_info","probe_echo","probe_validation","probe_evidence_page","probe_denied_operation"]
        rules=["MCPTool(wpai_probe__"+name+")" for name in names]
        txt=("[plugins]\ndisabled = [\"cloudflare\"]\n"
             "[permission]\n"
             f"allow = {json.dumps(rules)}\n"
             'deny = ["Bash","Read","Edit","Grep","WebFetch","WebSearch"]\n'
             "[mcp_servers.wpai_probe]\n"
             f"command = {json.dumps(entry['command'])}\n"
             f"args = {json.dumps(entry['args'])}\n"
             "startup_timeout_sec = 8\ntool_timeout_sec = 12\n")
        (config/"config.toml").write_text(txt,encoding="utf-8")
    else:
        (run/"claude-mcp.json").write_text(json.dumps({"mcpServers":{"wpai_probe":entry}},indent=2)+"\n",encoding="utf-8")

config_files = [
    "~/.grok/config.toml", "~/.grok/managed_config.toml", "~/.grok/requirements.toml",
    "~/.claude.json","~/.claude/settings.json","~/.claude/settings.local.json",
]
snapshot={}
for path in config_files:
    file=Path(path).expanduser()
    snapshot[path]=hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
(run/"config-before.json").write_text(json.dumps(snapshot,indent=2), encoding="utf-8")
print(str(run),flush=True)
grok=shutil.which("grok.exe")
env=os.environ.copy()
env.update(GROK_DISABLE_AUTOUPDATER="1")
out=subprocess.run([grok,"--no-auto-update","inspect","--json"],cwd=run/"grok",env=env,
                   text=True,capture_output=True,timeout=12,check=False)
if out.returncode:
    print("inspect exit", out.returncode, out.stderr[:500])
    sys.exit(out.returncode)
d=json.loads(out.stdout)
p=d["permissions"]
m={"projectRootMatches":d.get("projectRoot")==str(run/"grok"),"projectTrusted":d.get("projectTrusted"),
   "configurationLayers":[{"role":i["role"],"filename":Path(i["path"]).name} for i in d["configSources"]["layers"]],
   "mcp":[{"name":i["name"],"transport":i["transport"],"source":i["source"]} for i in d["mcpServers"]],
   "plugins":[{"name":i["name"],"enabled":i["enabled"],"scope":i["scope"]} for i in d["plugins"]],
   "hooks":len(d["hooks"]),"managedOnly":p["mcpManagedServersOnly"],"managedSettingsActive":p["managedSettingsActive"],
   "permissionLoaded":p["loaded"],"permissionSkipped":p["skipped"],"configWarnings":len(d["configWarnings"])}
(run/"grok-inspect-summary.json").write_text(json.dumps(m,indent=2),encoding="utf-8")
print(json.dumps(m,indent=2))

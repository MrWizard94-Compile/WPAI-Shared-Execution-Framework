from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import mkdtemp
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


WORK = Path(__file__).resolve().parent
OUT = WORK.parent / "outputs"
SOURCE = WORK / "wpai-exec"
NAMES = ("README.md", "repo_health.py", "tests/test_repo_health.py", "wpai_exec.py")
FILES = {name: (SOURCE / name).read_bytes() for name in NAMES}
FILES["W1-objective.txt"] = (OUT / "W1-objective.txt").read_bytes()


def digest(content):
    return sha256(content).hexdigest()


FILES["MANIFEST.sha256"] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(FILES.items())).encode()


def build(path):
    with ZipFile(path, "w") as archive:
        for name, data in sorted(FILES.items()):
            member = ZipInfo(f"wpai-exec/{name}", date_time=(2026, 11, 26, 0, 0, 0))
            member.create_system = 3
            member.external_attr = 0o100644 << 16
            archive.writestr(member, data, compress_type=ZIP_DEFLATED, compresslevel=9)


scratch = Path(mkdtemp(prefix="stage1-package-", dir=WORK))
candidate, rebuild = scratch / "candidate.zip", scratch / "rebuild.zip"
build(candidate)
build(rebuild)
assert candidate.read_bytes() == rebuild.read_bytes(), "archive was not reproducible"
with ZipFile(candidate) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == {f"wpai-exec/{name}" for name in FILES}
    archive.extractall(scratch)
project = scratch / "wpai-exec"
assert {name: (project / name).read_bytes() for name in FILES} == FILES
with (scratch / "unittest.log").open("wb") as log:
    for runtime in ([sys.executable], ["py", "-3.10"]):
        subprocess.run([*runtime, "-B", "-W", "error", "-m", "unittest", "discover", "-s", "tests", "-v"],
                       cwd=project, stdout=log, stderr=subprocess.STDOUT, timeout=20, check=True)
reference = subprocess.check_output([sys.executable, "-B", str(WORK / "verify-stage-1.py"), str(project)],
                                    text=True, timeout=75).strip()
live = subprocess.check_output(["py", "-3.10", "-B", str(project / "wpai_exec.py"), "repo_health_v1",
                                "--project", "trackforge"], timeout=28)
assert json.loads(live)["status"] == "OK" and len(json.loads(live)["facts"]) == 12
rejected = subprocess.run([sys.executable, "-B", str(project / "wpai_exec.py"), "repo_health_v1", "--project",
                           "other"], capture_output=True, timeout=5, check=False)
assert rejected.returncode == 2 and json.loads(rejected.stdout)["status"] == "DENIED"
archive = OUT / "wpai-exec-stage-1.zip"
archive.write_bytes(candidate.read_bytes())
record = {"archive_sha256": digest(archive.read_bytes()), "reproducible": True, "archive_members": sorted(FILES),
          "test_log": str(scratch / "unittest.log"), "integration_evidence": reference,
          "cli_observed_fields": sum(field["status"] == "observed" for field in json.loads(live)["facts"].values()),
          "cli_denial_exit": rejected.returncode, "manifest": FILES["MANIFEST.sha256"].decode()}
(scratch / "package.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(scratch)
print(json.dumps(record, indent=2))

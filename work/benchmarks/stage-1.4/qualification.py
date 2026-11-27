"""Reproduce all offline scenarios, including an observer terminated mid-record."""

from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from observer import RUN_SECONDS, child_environment, observe
from windows import Job
from witness_record import SCENARIOS, validate


HERE = Path(__file__).resolve().parent
EXPECTED = {
    "normal": "observed_success", "server_zero": "observed_success",
    "server_nonzero": "observed_failure", "wrapper_only": "observed_failure",
    "external_tree": "observed_failure", "descendant": "observed_failure", "local_pipe_close": "observed_failure",
    "channel_broken": "unavailable", "observer_crash": "incomplete", "missing_registration": "unavailable",
    "missing_exit": "unavailable", "identity_mismatch": "invalid", "timeout": "observed_failure",
}


def crash_observer(path):
    # A parent-only containment job verifies that the crashed observer leaves no processes.
    gate = ("import os,runpy,sys\n"
            "assert os.read(0,1)==b'G'\n"
            "sys.path.insert(0,sys.argv[1])\n"
            "sys.argv=sys.argv[2:]\n"
            "runpy.run_path(sys.argv[0],run_name='__main__')\n")
    argv = [sys.executable, "-I", "-S", "-B", "-W", "error", "-c", gate, str(HERE), str(HERE / "observer.py"),
            "observer_crash", "--record", str(path)]
    with Job() as guard, subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, bufsize=0, env=child_environment()) as observer:
        try:
            guard.assign(observer.pid)
            if observer.stdin.write(b"G") != 1:
                raise OSError("Observer crash test gate write failed")
            code = observer.wait(timeout=RUN_SECONDS + 2)
            end = time.monotonic() + 3
            while guard.accounting().active and time.monotonic() < end:
                time.sleep(0.005)
            active = guard.accounting().active
            if (code, active) != (91, 0):
                raise RuntimeError("Observer crash did not leave an empty parent job")
        finally:
            if observer.poll() is None:
                observer.kill()
                observer.wait(timeout=3)
    return {**validate(path), "test_parent_after_observer_exit": {"observer_exit_code": code, "active": active}}


def run_case(scenario, path):
    if scenario == "observer_crash":
        return crash_observer(path)
    return observe(scenario, path)


def qualify():
    evidence = {}
    with TemporaryDirectory(prefix="wpai-witness-evidence-") as private:
        for scenario in SCENARIOS:
            result = run_case(scenario, Path(private) / (scenario + ".jsonl"))
            if result["status"] != EXPECTED[scenario]:
                raise RuntimeError(f"{scenario}: expected {EXPECTED[scenario]}, observed {result['status']}")
            evidence[scenario] = result
    return evidence

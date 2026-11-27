"""Windows observer and fixed offline qualification scenarios."""

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from uuid import uuid4

import actors
import windows as win
from witness_record import Ledger, SCENARIOS, canonical, digest, validate


WAIT_SECONDS = 6
RUN_SECONDS = 24
POLL_SECONDS = 0.005
WRAPPER = "wrapper"
SERVER = "server"


def child_environment(directory=None):
    # Absolute Python and fixture paths require no PATH or provider environment.
    settings = {"SystemRoot": os.environ["SystemRoot"]}
    if directory is not None:
        settings.update(TEMP=str(directory), TMP=str(directory))
    return settings


class Observer:
    def __init__(self, ledger, job, resources):
        self.ledger = ledger
        self.job = job
        self.resources = resources
        self.deadline = time.monotonic() + RUN_SECONDS
        self.children = {}
        self.processes = {}
        self.pipes = {}
        self.recorded_pipes = set()
        self.registered = set()
        self.exits = set()
        self.observer_handle = win.current_process()
        self.observer_identity = win.identity(self.observer_handle)

    def tokens(self, identity):
        material = canonical([self.ledger.run_id, identity.pid, identity.created])
        return {"identity": digest(b"process:" + material), "created": digest(b"creation:" + material)}

    def start(self, scenario):
        self.ledger.add("observer_started", scenario=scenario, **self.tokens(self.observer_identity),
                        outside_job=not win.in_job(self.observer_handle, self.job))

    def finish(self):
        self.ledger.add("observer_finalized", identity=self.tokens(win.identity(self.observer_handle))["identity"],
                        outside_job=not win.in_job(self.observer_handle, self.job), source="observer_terminal_record")

    def issue(self, category, code):
        self.ledger.add("issue", **{"class": category, "code": code})

    def write(self, role, payload):
        if len(payload) > 1024 or self.children[role].stdin.write(payload) != len(payload):
            raise OSError("Synthetic channel write failed")

    def retain(self, role, process, source, *, record=True):
        self.resources.callback(process.close)
        if win.in_job(process.handle, self.job) != (role != "owner"):
            raise ValueError("Process is outside its intended ownership boundary")
        self.processes[role] = process
        if record:
            self.ledger.add("process_registered", role=role, **self.tokens(process.identity),
                            in_job=role != "owner", source=source)
            self.registered.add(role)

    def launch(self, role, fixture_role=None, arguments=(), *, legacy_env=None, record=True, owner_handle=None):
        """Hold the startup gate until the new process is contained and identified."""
        argv = [sys.executable, "-I", "-S", "-B", "-W", "error", str(actors.ACTORS), fixture_role or role, *arguments]
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL if role == "owner" or fixture_role == "legacy" else subprocess.PIPE,
                                   bufsize=0, close_fds=True, env=legacy_env or child_environment(),
                                   startupinfo=win.owner_startup(owner_handle) if owner_handle is not None else None)
        self.children[role] = process
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                self.resources.callback(stream.close)
        if role != "owner":
            self.job.assign(process.pid)
        # Check the reopened limited-access handle against the original CreateProcess handle.
        retained = win.Process(process.pid, expected=win.identity(int(process._handle)))
        self.retain(role, retained, "created_handle", record=record)
        self.pipes[f"{role}_control" if role == "owner" else f"{role}_stdout"] = win.Pipe(process.stdout)
        if process.stderr is not None:
            self.pipes[f"{role}_control"] = win.Pipe(process.stderr)
        self.write(role, b"G")

    def attach_single_job_member(self, role):
        known = {item.identity.pid for key, item in self.processes.items() if key != "owner"}
        self.until(lambda: bool(win.members(self.job) - known))
        extra = win.members(self.job) - known
        if len(extra) != 1:
            raise ValueError("Controlled job did not expose one additional member")
        pid = next(iter(extra))
        retained = win.Process(pid)
        try:
            accounting = self.job.accounting()
            if (win.members(self.job) != known | {pid} or accounting.total != len(known) + 1
                    or not win.in_job(retained.handle, self.job)
                    or retained.identity.pid != pid or retained.identity.created < self.processes[WRAPPER].identity.created
                    or retained.signaled()):
                raise ValueError("Additional job member identity is inconsistent")
        except BaseException:
            retained.close()
            raise
        self.retain(role, retained, "bounded_job_membership")

    def poll(self):
        for name, pipe in self.pipes.items():
            pipe.poll()
            if pipe.terminal and name not in self.recorded_pipes:
                outcome, error, source = pipe.terminal
                self.ledger.add("pipe_terminal", channel=name, outcome=outcome, winerror=error, source=source)
                self.recorded_pipes.add(name)

    def until(self, predicate, seconds=WAIT_SECONDS):
        end = min(self.deadline, time.monotonic() + seconds)
        while True:
            self.poll()
            if predicate():
                return
            if time.monotonic() >= end:
                raise TimeoutError("Bounded synthetic observation expired")
            time.sleep(POLL_SECONDS)

    def expect(self, pipe, payload):
        source = self.pipes[pipe]
        self.until(lambda: len(source.received) >= len(payload) or source.terminal is not None)
        if source.received != payload:
            raise ValueError("Unexpected fixed synthetic payload")

    def check_exit(self, role, *, fetch_code=True):
        process = self.processes[role]
        self.until(process.signaled)
        if role not in self.registered or role in self.exits:
            return
        self.ledger.add("handle_signaled", role=role, source="WaitForSingleObject")
        if fetch_code:
            self.ledger.add("process_exit", role=role, code=process.exit_code(), source="GetExitCodeProcess")
        else:
            self.issue("unavailable", "missing_exit")
        self.exits.add(role)

    def checkpoint(self, name):
        accounting = self.job.accounting()
        self.ledger.add("job_accounting", checkpoint=name, total=accounting.total, active=accounting.active,
                        source="QueryInformationJobObject")

    def stop_job(self):
        self.ledger.add("force_requested", target="job", source="observer_control")
        self.job.terminate()

    def active_after_wrapper(self, role):
        if self.processes[role].signaled():
            raise ValueError("Expected an independently live process after wrapper exit")
        self.ledger.add("process_active", role=role, checkpoint="after_wrapper_exit", source="WaitForSingleObject")
        self.checkpoint("after_wrapper_exit")

    def observe_control(self, role):
        pipe = self.pipes[f"{role}_control"]
        if pipe.received == actors.CONTROL:
            for marker in ("stdin_eof", "stdout_finished"):
                self.ledger.add("fixture_marker", role=role, marker=marker, source="trusted_fixture_control_pipe")
        elif not pipe.received and pipe.terminal and pipe.terminal[0] in ("peer_closed", "zero_read"):
            self.issue("unavailable", "channel_disconnected")
        else:
            self.issue("invalid", "invalid_control_message")

    def normal_actors(self, scenario):
        self.launch(WRAPPER, arguments=("normal",))
        server_mode = {"channel_broken": "no_control", "server_nonzero": "nonzero"}.get(scenario, "normal")
        self.launch(SERVER, arguments=(server_mode,), record=scenario != "missing_registration")
        self.checkpoint("registered")
        self.write(WRAPPER, actors.REQUEST)
        self.expect("wrapper_stdout", actors.REQUEST)
        self.write(SERVER, bytes(self.pipes["wrapper_stdout"].received))
        self.expect("server_stdout", actors.RESPONSE)
        if scenario == "identity_mismatch":
            observed = self.processes[SERVER].identity
            try:
                mismatched = win.Process(observed.pid, expected=win.Identity(observed.pid, observed.created + 1))
            except ValueError:
                self.issue("invalid", "identity_mismatch")
            else:
                mismatched.close()
                raise RuntimeError("Creation identity mismatch was accepted")
        order = (SERVER, WRAPPER) if scenario.startswith("server_") else (WRAPPER, SERVER)
        for role in order:
            self.children[role].stdin.close()
            if role in self.registered:
                self.ledger.add("stdin_writer_closed", role=role, source="observer_closed_writer")
            self.check_exit(role, fetch_code=not (role == SERVER and scenario == "missing_exit"))
            self.until(lambda: self.pipes[f"{role}_control"].terminal and self.pipes[f"{role}_stdout"].terminal)
            if role in self.registered:
                self.observe_control(role)
            else:
                self.issue("unavailable", "missing_registration")
    def external_tree(self):
        directory = Path(self.resources.enter_context(TemporaryDirectory(prefix="wpai-witness-")))
        receipt = directory / "in-band.json"
        self.launch(WRAPPER, "legacy", (str(receipt),), legacy_env=child_environment(directory))
        self.write(WRAPPER, actors.INITIALIZE)
        output = self.pipes["wrapper_stdout"]
        self.until(lambda: b"\n" in output.received or output.terminal is not None)
        answer = json.loads(output.received)
        if (answer.get("jsonrpc") != "2.0" or answer.get("id") != 1
                or answer.get("result", {}).get("protocolVersion") != "2025-06-18"):
            raise ValueError("Pinned fixture did not negotiate its synthetic protocol")
        self.attach_single_job_member(SERVER)
        self.checkpoint("registered")
        handle = win.duplicate_terminate_handle(self.job)
        try:
            self.launch("owner", arguments=(str(handle),), owner_handle=handle)
        finally:
            win.checked(win.close_handle(handle))
        self.ledger.add("force_requested", target="job", source="external_owner")
        self.write("owner", b"K")
        self.expect("owner_control", actors.ACK)
        self.ledger.add("owner_acknowledged", source="owner_control_pipe")
        self.check_exit(WRAPPER)
        self.check_exit(SERVER)
        self.ledger.add("force_requested", target="owner", source="observer_control")
        self.children["owner"].kill()
        self.check_exit("owner")
        self.until(lambda: output.terminal is not None and self.pipes["owner_control"].terminal is not None)
        self.ledger.add("receipt_checked", present=receipt.exists(), source="observer_checked_legacy_receipt_path")

    def blocked_actors(self, scenario):
        self.launch(WRAPPER, "descendant_wrapper" if scenario == "descendant" else WRAPPER, ("blocked",))
        self.launch(SERVER, arguments=("blocked",))
        self.expect("wrapper_stdout", actors.READY)
        self.expect("server_stdout", actors.READY)
        if scenario == "descendant":
            self.attach_single_job_member("descendant")
        self.checkpoint("registered")
        if scenario == "observer_crash":
            # Flushes already reached disk. Last job handle closes at process exit.
            os._exit(91)
        if scenario == "wrapper_only":
            self.ledger.add("force_requested", target="wrapper", source="observer_control")
            self.children[WRAPPER].kill()
            self.check_exit(WRAPPER)
            self.active_after_wrapper(SERVER)
        elif scenario == "descendant":
            self.write(WRAPPER, b"X")
            self.check_exit(WRAPPER)
            self.active_after_wrapper("descendant")
        elif scenario == "local_pipe_close":
            if self.processes[SERVER].signaled():
                raise ValueError("Pipe writer exited before observer closed its read endpoint")
            self.pipes["server_stdout"].close_unread()
            self.poll()
        elif scenario == "timeout":
            try:
                self.until(self.processes[SERVER].signaled, seconds=0.15)
            except TimeoutError:
                self.issue("failure", "timeout")
            else:
                raise ValueError("Synthetic server did not remain active")
        self.stop_job()
        for role in self.processes:
            self.check_exit(role)

    def finalize_observation(self):
        self.until(lambda: self.job.accounting().active == 0 and all(pipe.terminal for pipe in self.pipes.values()))
        self.checkpoint("final")

    def cleanup(self):
        # The observer owns this job only. Stop the separate owner first if it still holds a duplicate.
        owner = self.children.get("owner")
        if owner is not None and owner.poll() is None:
            owner.kill()
        if self.job.accounting().active:
            self.job.terminate()
        for process in self.children.values():
            if process.poll() is None:
                process.kill()
            process.wait(timeout=WAIT_SECONDS)


def observe(scenario, path):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown offline scenario")
    with win.open_evidence(path) as stream, win.Job() as job, ExitStack() as resources:
        observer = Observer(Ledger(stream, uuid4().hex), job, resources)
        observer.start(scenario)
        try:
            if scenario == "external_tree":
                observer.external_tree()
            elif scenario in ("wrapper_only", "descendant", "local_pipe_close", "observer_crash", "timeout"):
                observer.blocked_actors(scenario)
            else:
                observer.normal_actors(scenario)
            observer.finalize_observation()
        except (TimeoutError, OSError):
            observer.issue("unavailable", "observation_api_failed")
        except (ValueError, TypeError, KeyError):
            observer.issue("invalid", "unexpected_fixture_payload")
        finally:
            observer.cleanup()
        observer.finish()
    return validate(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--record", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(observe(args.scenario, args.record), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

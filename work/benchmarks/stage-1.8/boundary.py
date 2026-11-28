"""Fixed bootstrap and rights-limited Windows boundaries around the Stage 1.6 actors."""

import _winapi
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import subprocess
import sys
import time


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
STAGE_16 = SOURCE.parent / "stage-1.6"
sys.path.append(str(STAGE_16))

import win
from contract import canonical, parse, require


CASES = ("normal", "before_launch", "actors_verified", "in_flight", "response_verified")
JOBS = ("subject", "fixture", "guard")
ACTORS = ("owner", "server", "root", "relay")
MEMBERSHIP = {
    "witness": (), "controller": ("guard",), "owner": ("guard",),
    "server": ("fixture", "guard"), "root": ("subject", "guard"), "relay": ("subject", "guard"),
}
QUERY = 0x04
ASSIGN = 0x01
TERMINATE = 0x08
OBSERVE_PROCESS = 0x101000  # PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE
CONTROLLER_MASKS = {"subject": QUERY | ASSIGN, "fixture": QUERY | ASSIGN}
WITNESS_MASKS = {"subject": QUERY, "fixture": QUERY, "guard": QUERY | TERMINATE}
INJECTED_EXIT = 93
RECOVERED_EXIT = 124
RECOVERY_MS = 8000
FRAME_LIMIT = 1024
RUN_SECONDS = 38


class ObjectBasic(c.Structure):
    _fields_ = [("attributes", w.ULONG), ("access", w.ULONG), ("handles", w.ULONG), ("pointers", w.ULONG),
                ("reserved", w.ULONG * 10)]


query_object = c.WinDLL("ntdll").NtQueryObject
query_object.restype = w.LONG
query_object.argtypes = (w.HANDLE, c.c_int, c.c_void_p, w.ULONG, c.POINTER(w.ULONG))


def rights(handle):
    result = ObjectBasic()
    require(query_object(handle, 0, c.byref(result), c.sizeof(result), None) == 0,
            "Cannot inspect granted access on the owned handle")
    return result.access


class JobView(win.Job):
    """Use accepted accounting operations on a limited, already owned handle."""

    def __init__(self, handle):
        self.handle = handle


def checked_jobs(handles, expected):
    jobs = dict(zip(expected, (JobView(handle) for handle in handles), strict=True))
    for name, job in jobs.items():
        require(rights(job.handle) == expected[name], f"Unexpected {name} granted job rights")
    return jobs


def snapshot(job):
    accounting = job.accounting()
    pids = win.members(job)
    require(accounting.active == len(pids), "Job membership changed during the independent sample")
    return pids, accounting.active, accounting.total


def wait_until(predicate, deadline):
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError("Owned Windows observation deadline expired")
        time.sleep(0.002)


def send(handle, **fields):
    frame = canonical(fields) + b"\n"
    require(len(frame) <= FRAME_LIMIT, "Private control frame too large")
    win.write(handle, frame)


def receive(reader, deadline):
    frame = reader.line(deadline)
    if not frame:
        require(reader.terminal in (0, 38, 109), "Private channel did not reach terminal ReadFile")
        return None
    require(len(frame) <= FRAME_LIMIT, "Private control frame too large")
    row = parse(frame)
    require(isinstance(row, dict) and canonical(row) + b"\n" == frame, "Noncanonical private control frame")
    return row


def received(stack, values, count):
    require(len(values) == count, "Invalid inherited handle count")
    handles = tuple(int(value) for value in values)
    require(len(set(handles)) == count and all(handle > 0 for handle in handles), "Invalid inherited handles")
    for handle in handles:
        os.set_handle_inheritable(handle, False)
        stack.callback(win.Handle(handle).close)
    return handles


def launch(role, scenario, handles, scratch):
    """Start one of two fixed Python bootstraps suspended, with only the listed handles."""
    require(role in ("controller", "independent") and scenario in CASES, "Unexpected local stage role")
    script = SOURCE / (role + ".py")
    values = [handle.value for handle in handles]
    args = [sys.executable, "-I", "-S", "-B", "-W", "error", str(script), scenario, str(scratch),
            *(str(value) for value in values)]
    startup = subprocess.STARTUPINFO()
    startup.lpAttributeList = {"handle_list": values}
    try:
        for value in values:
            os.set_handle_inheritable(value, True)
        process, thread, pid, _ = _winapi.CreateProcess(
            sys.executable, subprocess.list2cmdline(args), None, None, True, win.CREATE_FLAGS,
            {"SystemRoot": os.environ["SystemRoot"]}, str(SOURCE), startup)
    finally:
        for value in values:
            os.set_handle_inheritable(value, False)
    return win.Child(process, thread, pid)


def deny_network():
    def audit(event, _args):
        if event.startswith("socket."):
            raise PermissionError("Stage 1.8 has no network route")

    sys.addaudithook(audit)
    try:
        sys.audit("socket.__new__")
    except PermissionError:
        return
    raise RuntimeError("Local-only network guard did not take effect")


def fixed_actor_command(application, command):
    require(application == sys.executable and any(
        command.startswith(subprocess.list2cmdline(
            [sys.executable, "-I", "-S", "-B", "-W", "error", str(STAGE_16 / "actors.py"), role]) + " ")
        for role in ("owner", "subject")), "Unexpected controller executable or actor")


def restrict_controller_launches():
    original = _winapi.CreateProcess

    def guarded(application, command, *args):
        fixed_actor_command(application, command)
        return original(application, command, *args)

    _winapi.CreateProcess = guarded

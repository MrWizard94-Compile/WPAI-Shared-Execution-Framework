"""Narrow Win32 access to handles belonging to this synthetic harness."""

import ctypes as c
from ctypes import wintypes as w
from dataclasses import dataclass
import msvcrt
import os
from pathlib import Path
import subprocess
import sys


sys.path.append(str(Path(__file__).resolve().parents[1] / "stage-1.3.1"))
from winjob import (Job, bind, checked, close_handle, open_process, query_job, read_file, terminate_job,
                    ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF)


WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x100000
JOB_OBJECT_TERMINATE = 0x8
MAX_JOB_MEMBERS = 8
PIPE_BUDGET = 8192

wait_for_one = bind("WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
get_exit = bind("GetExitCodeProcess", w.BOOL, w.HANDLE, c.POINTER(w.DWORD))
get_pid = bind("GetProcessId", w.DWORD, w.HANDLE)
get_times = bind("GetProcessTimes", w.BOOL, w.HANDLE, *([c.POINTER(w.FILETIME)] * 4))
is_in_job = bind("IsProcessInJob", w.BOOL, w.HANDLE, w.HANDLE, c.POINTER(w.BOOL))
current_process = bind("GetCurrentProcess", w.HANDLE)
duplicate = bind("DuplicateHandle", w.BOOL, w.HANDLE, w.HANDLE, w.HANDLE, c.POINTER(w.HANDLE),
                 w.DWORD, w.BOOL, w.DWORD)
peek_pipe = bind("PeekNamedPipe", w.BOOL, w.HANDLE, c.c_void_p, w.DWORD, c.c_void_p, c.POINTER(w.DWORD), c.c_void_p)
create_file = bind("CreateFileW", w.HANDLE, w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE)


@dataclass(frozen=True)
class Identity:
    pid: int
    created: int


def identity(handle):
    created, ended, kernel, user = (w.FILETIME() for _ in range(4))
    checked(get_times(handle, c.byref(created), c.byref(ended), c.byref(kernel), c.byref(user)))
    return Identity(checked(get_pid(handle)), (created.dwHighDateTime << 32) | created.dwLowDateTime)


def in_job(handle, job):
    member = w.BOOL()
    checked(is_in_job(handle, job.handle, c.byref(member)))
    return bool(member.value)


def select_identity(actual, expected):
    if actual != expected:
        raise ValueError("Process creation identity mismatch")


class Process:
    """Own a noninheritable wait/query-only process handle."""

    def __init__(self, pid, *, expected=None):
        self.handle = checked(open_process(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid))
        try:
            self.identity = identity(self.handle)
            if expected is not None:
                select_identity(self.identity, expected)
        except BaseException:
            self.close()
            raise

    def close(self):
        checked(close_handle(self.handle))

    def signaled(self):
        result = wait_for_one(self.handle, 0)
        if result not in (WAIT_OBJECT_0, WAIT_TIMEOUT):
            raise c.WinError(c.get_last_error())
        return result == WAIT_OBJECT_0

    def exit_code(self):
        if not self.signaled():
            raise ValueError("Process exit requested before the handle was signaled")
        code = w.DWORD()
        checked(get_exit(self.handle, c.byref(code)))
        return code.value


class Members(c.Structure):
    _fields_ = [("assigned", w.DWORD), ("listed", w.DWORD), ("pids", c.c_size_t * MAX_JOB_MEMBERS)]


def members(job):
    """Inspect only this job, with a hard cap. Never enumerate the system."""
    result = Members()
    checked(query_job(job.handle, 3, c.byref(result), c.sizeof(result), None))
    if result.assigned != result.listed or result.listed > MAX_JOB_MEMBERS:
        raise ValueError("Job membership snapshot unavailable or above bound")
    return set(result.pids[:result.listed])


def duplicate_terminate_handle(job):
    peer = current_process()
    result = w.HANDLE()
    checked(duplicate(peer, job.handle, peer, c.byref(result), JOB_OBJECT_TERMINATE, True, 0))
    return result.value


def owner_startup(handle):
    startup = subprocess.STARTUPINFO()
    startup.lpAttributeList = {"handle_list": [handle]}
    return startup


def open_evidence(path):
    """Exclusive writer, read sharing only, no inheritance or replacement while open."""
    handle = create_file(str(path), 0x40000000, 1, None, 1, 0x80, None)
    if handle == w.HANDLE(-1).value:
        raise c.WinError(c.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        close_handle(handle)
        raise
    return os.fdopen(fd, "wb", buffering=0)


class Pipe:
    """One private synchronous reader. Peek bounds data reads and never stands in for EOF."""

    def __init__(self, file):
        self.file = file
        self.terminal = None
        self.received = bytearray()

    def poll(self):
        if self.terminal is not None:
            return
        available = w.DWORD()
        handle = msvcrt.get_osfhandle(self.file.fileno())
        if not peek_pipe(handle, None, 0, None, c.byref(available), None):
            error = c.get_last_error()
            if error not in (ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF):
                self.terminal = ("read_error", error, "PeekNamedPipe")
                return
            # Call ReadFile even when Peek reports that no writers remain.
        elif not available.value:
            return
        size = min(max(available.value, 1), 4096)
        buffer, read = c.create_string_buffer(size), w.DWORD()
        if not read_file(handle, buffer, size, c.byref(read), None):
            error = c.get_last_error()
            self.terminal = ("peer_closed" if error in (ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF) else "read_error",
                             error, "ReadFile")
        elif read.value == 0:
            self.terminal = ("zero_read", 0, "ReadFile")
        elif len(self.received) + read.value > PIPE_BUDGET:
            self.terminal = ("budget_exceeded", 0, "ReadFile")
        else:
            self.received.extend(buffer.raw[:read.value])

    def close_unread(self):
        if self.terminal is not None:
            raise ValueError("Expected an open read endpoint")
        self.file.close()
        self.terminal = ("local_close", 0, "observer_closed_reader")

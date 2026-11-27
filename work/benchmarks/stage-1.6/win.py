"""Bounded Win32 handles for the fixed synthetic process tree."""

import _winapi
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.append(str(Path(__file__).resolve().parents[1] / "stage-1.4"))
from windows import (Identity, Process, close_handle, current_process, duplicate, identity, in_job, members,
                     open_evidence, peek_pipe, wait_for_one, WAIT_OBJECT_0, WAIT_TIMEOUT)
from winjob import (Job as OwnedJob, Limits, assign_process, bind, checked, create_job, set_job, read_file, write_file,
                    terminate_job, ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF)


SOURCE = Path(__file__).resolve().parent
READ_LIMIT = 32768
PIPE_CAPACITY = 65536
FORCED = 124
OWNER_LOST = 125
TIMEOUT = 8
CREATE_FLAGS = _winapi.DETACHED_PROCESS | 0x00000004  # CREATE_SUSPENDED

resume_thread = bind("ResumeThread", w.DWORD, w.HANDLE)
terminate_process = bind("TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
local_free = bind("LocalFree", w.HANDLE, w.HANDLE)
LABEL_SECURITY_INFORMATION = 0x10
security = c.WinDLL("advapi32", use_last_error=True)


def security_api(name, result, *args):
    function = getattr(security, name)
    function.restype = result
    function.argtypes = args
    return function


convert_sid = security_api("ConvertStringSidToSidW", w.BOOL, w.LPCWSTR, c.POINTER(c.c_void_p))
length_sid = security_api("GetLengthSid", w.DWORD, c.c_void_p)
open_token = security_api("OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, c.POINTER(w.HANDLE))
set_token = security_api("SetTokenInformation", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
get_token = security_api("GetTokenInformation", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD))
sid_count = security_api("GetSidSubAuthorityCount", c.POINTER(c.c_ubyte), c.c_void_p)
sid_part = security_api("GetSidSubAuthority", c.POINTER(w.DWORD), c.c_void_p, w.DWORD)
convert_sddl = security_api("ConvertStringSecurityDescriptorToSecurityDescriptorW", w.BOOL, w.LPCWSTR,
                           w.DWORD, c.POINTER(c.c_void_p), c.c_void_p)
get_sacl = security_api("GetSecurityDescriptorSacl", w.BOOL, c.c_void_p, c.POINTER(w.BOOL),
                        c.POINTER(c.c_void_p), c.POINTER(w.BOOL))
set_named_security = security_api("SetNamedSecurityInfoW", w.DWORD, w.LPWSTR, c.c_int, w.DWORD,
                                  c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p)


class Label(c.Structure):
    _fields_ = [("sid", c.c_void_p), ("attributes", w.DWORD)]


def protect_scratch(path):
    """Apply medium no-read-up/no-write-up to a newly created private test directory."""
    descriptor = c.c_void_p()
    checked(convert_sddl("S:(ML;OICI;NWNR;;;ME)", 1, c.byref(descriptor), None))
    try:
        present, defaulted, sacl = w.BOOL(), w.BOOL(), c.c_void_p()
        checked(get_sacl(descriptor, c.byref(present), c.byref(sacl), c.byref(defaulted)))
        error = set_named_security(str(path), 1, LABEL_SECURITY_INFORMATION, None, None, None, sacl)
        if error:
            raise c.WinError(error)
    finally:
        local_free(descriptor)


@contextmanager
def process_token(process, access):
    token = w.HANDLE()
    checked(open_token(process, access, c.byref(token)))
    try:
        yield token.value
    finally:
        checked(close_handle(token))


def integrity(process):
    with process_token(process, 0x0008) as token:  # TOKEN_QUERY
        data, size = c.create_string_buffer(256), w.DWORD()
        checked(get_token(token, 25, data, len(data), c.byref(size)))  # TokenIntegrityLevel
        sid = Label.from_buffer(data).sid
        return sid_part(sid, sid_count(sid)[0] - 1)[0]


def lower_integrity(process):
    sid = c.c_void_p()
    checked(convert_sid("S-1-16-4096", c.byref(sid)))
    try:
        with process_token(process, 0x0088) as token:  # TOKEN_ADJUST_DEFAULT | TOKEN_QUERY
            label = Label(sid, 0x20)  # SE_GROUP_INTEGRITY
            checked(set_token(token, 25, c.byref(label), c.sizeof(label) + length_sid(sid)))
        if integrity(process) != 4096:
            raise ValueError("Force process integrity did not become low")
    finally:
        local_free(sid)


class Job(OwnedJob):
    def __init__(self, limit):
        self.limit = limit

    def __enter__(self):
        self.handle = checked(create_job(None, None))
        try:
            limits = Limits()
            limits.basic.flags = 0x2008  # KILL_ON_JOB_CLOSE and ACTIVE_PROCESS; no breakaway.
            limits.basic.max_active = self.limit
            checked(set_job(self.handle, 9, c.byref(limits), c.sizeof(limits)))
        except OSError:
            close_handle(self.handle)
            raise
        return self


class Handle:
    def __init__(self, value):
        self.value = value

    def close(self):
        if self.value is not None:
            value, self.value = self.value, None
            checked(close_handle(value))


def pipe():
    return tuple(Handle(handle) for handle in _winapi.CreatePipe(None, PIPE_CAPACITY))


def copy_handle(value, access=None):
    peer, copied = current_process(), w.HANDLE()
    checked(duplicate(peer, value, peer, c.byref(copied), access or 0, False, 2 if access is None else 0))
    return Handle(copied.value)


def write(handle, data):
    if not 0 < len(data) < READ_LIMIT:
        raise ValueError("Synthetic write exceeded its fixed bound")
    written = w.DWORD()
    checked(write_file(handle, data, len(data), c.byref(written), None))
    if written.value != len(data):
        raise OSError("Short synthetic pipe write")


def read(handle, size):
    data, count = c.create_string_buffer(size), w.DWORD()
    if not read_file(handle, data, size, c.byref(count), None):
        error = c.get_last_error()
        if error not in (ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF):
            raise c.WinError(error)
        return b"", error
    return data.raw[:count.value], None if count.value else 0


class Reader:
    """Line framing for a fixed transaction, preserving original bytes and terminal OS status."""

    def __init__(self, handle):
        self.handle = handle
        self.buffer = bytearray()
        self.terminal = None

    def poll(self):
        if self.terminal is not None:
            return
        available = w.DWORD()
        if not peek_pipe(self.handle, None, 0, None, c.byref(available), None):
            error = c.get_last_error()
            if error not in (ERROR_BROKEN_PIPE, ERROR_HANDLE_EOF):
                raise c.WinError(error)
            self.receive(1)  # Only an actual ReadFile result can be a terminal event.
        elif available.value:
            self.receive(min(available.value, 4096))

    def receive(self, size):
        data, self.terminal = read(self.handle, size)
        self.buffer.extend(data)
        if len(self.buffer) >= READ_LIMIT:
            raise ValueError("Synthetic pipe read exceeded its fixed bound")

    def line(self, deadline=None):
        while True:
            position = self.buffer.find(b"\n")
            if position >= 0:
                line = bytes(self.buffer[:position + 1])
                del self.buffer[:position + 1]
                return line
            if self.terminal is not None:
                if self.buffer:
                    raise ValueError("Unterminated synthetic pipe frame")
                return b""
            if deadline is None:
                self.receive(4096)
            else:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Bounded pipe read expired")
                self.poll()
                time.sleep(0.002)


class Child:
    def __init__(self, process, thread, pid):
        self.process, self.thread = Handle(process), Handle(thread)
        self.pid = pid

    def start(self):
        if resume_thread(self.thread.value) != 1:
            raise OSError("Expected one suspended startup gate")
        self.thread.close()

    def kill(self, code=FORCED):
        if wait_for_one(self.process.value, 0) == WAIT_TIMEOUT:
            if not terminate_process(self.process.value, code):
                error = c.get_last_error()
                # A process already exiting (including from a Job termination) can reject termination.
                if error != 5 or wait_for_one(self.process.value, TIMEOUT * 1000) != WAIT_OBJECT_0:
                    raise c.WinError(error)

    def wait(self):
        if wait_for_one(self.process.value, TIMEOUT * 1000) != WAIT_OBJECT_0:
            raise TimeoutError("Bounded process wait expired")

    def close(self):
        try:
            self.kill()
            self.wait()
        finally:
            self.thread.close()
            self.process.close()


def spawn(role, handles, *, args=(), stdio=None, job_handle=None, low=False):
    """Pass only the listed anonymous-pipe handles and intentional standard handles."""
    values = [handle.value for handle in handles]
    argv = [sys.executable, "-I", "-S", "-B", "-W", "error", str(SOURCE / "actors.py"),
            role, *(str(x) for x in values), *args]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = _winapi.STARTF_USESTDHANDLES
    with open(os.devnull, "rb") as stdin, open(os.devnull, "wb") as discard:
        import msvcrt
        null_in, null_out = (msvcrt.get_osfhandle(file.fileno()) for file in (stdin, discard))
        startup.hStdInput, startup.hStdOutput = stdio or (null_in, null_out)
        startup.hStdError = null_out
        inherited = set(values) | {startup.hStdInput, startup.hStdOutput, startup.hStdError}
        startup.lpAttributeList = {"handle_list": sorted(inherited)}
        try:
            for handle in inherited:
                os.set_handle_inheritable(handle, True)
            process, thread, pid, _ = _winapi.CreateProcess(
                sys.executable, subprocess.list2cmdline(argv), None, None, True, CREATE_FLAGS,
                {"SystemRoot": os.environ["SystemRoot"]}, str(SOURCE), startup)
        finally:
            for handle in inherited:
                os.set_handle_inheritable(handle, False)
    child = Child(process, thread, pid)
    try:
        if job_handle is not None:
            checked(assign_process(job_handle, process))
        if low:
            lower_integrity(process)
    except BaseException:
        child.close()
        raise
    return child

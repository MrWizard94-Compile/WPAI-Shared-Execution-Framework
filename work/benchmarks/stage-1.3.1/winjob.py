"""Windows-only ownership and synchronous pipe cancellation for disposable fixtures."""

import ctypes as c
from ctypes import wintypes as w
import msvcrt


ERROR_HANDLE_EOF = 38
ERROR_BROKEN_PIPE = 109
ERROR_OPERATION_ABORTED = 995
ERROR_NOT_FOUND = 1168
THREAD_TERMINATE = 0x0001  # Required access for CancelSynchronousIo.


class BasicLimits(c.Structure):
    _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong), ("flags", w.DWORD),
                ("min_working_set", c.c_size_t), ("max_working_set", c.c_size_t), ("max_active", w.DWORD),
                ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]


class Limits(c.Structure):
    _fields_ = [("basic", BasicLimits), ("io", c.c_ulonglong * 6), ("process_memory", c.c_size_t),
                ("job_memory", c.c_size_t), ("peak_process_memory", c.c_size_t), ("peak_job_memory", c.c_size_t)]


class Accounting(c.Structure):
    _fields_ = [("times", c.c_longlong * 4), ("page_faults", w.DWORD), ("total", w.DWORD),
                ("active", w.DWORD), ("terminated", w.DWORD)]


kernel = c.WinDLL("kernel32", use_last_error=True)


def bind(name, result, *arguments):
    function = getattr(kernel, name)
    function.restype = result
    function.argtypes = arguments
    return function


create_job = bind("CreateJobObjectW", w.HANDLE, c.c_void_p, w.LPCWSTR)
set_job = bind("SetInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
query_job = bind("QueryInformationJobObject", w.BOOL, w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p)
open_process = bind("OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
assign_process = bind("AssignProcessToJobObject", w.BOOL, w.HANDLE, w.HANDLE)
terminate_job = bind("TerminateJobObject", w.BOOL, w.HANDLE, w.UINT)
close_handle = bind("CloseHandle", w.BOOL, w.HANDLE)
open_thread = bind("OpenThread", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
cancel_io = bind("CancelSynchronousIo", w.BOOL, w.HANDLE)
read_file = bind("ReadFile", w.BOOL, w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p)
write_file = bind("WriteFile", w.BOOL, w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p)


def checked(success):
    if not success:
        raise c.WinError(c.get_last_error())
    return success


def cancel_pending_io(handle):
    """Return whether a cancellation was requested. The I/O may still be running."""
    if cancel_io(handle):
        return True
    error = c.get_last_error()
    if error == ERROR_NOT_FOUND:
        return False
    raise c.WinError(error)


def read_pipe(stream, size):
    # CPython's Windows CRT path can map different Win32 errors to the same errno.
    # Keep the original status so an unrelated read/write error stays visible.
    buffer = c.create_string_buffer(size)
    count = w.DWORD()
    handle = msvcrt.get_osfhandle(stream.fileno())
    if not read_file(handle, buffer, size, c.byref(count), None):
        error = c.get_last_error()
        if error not in (ERROR_HANDLE_EOF, ERROR_BROKEN_PIPE):
            raise c.WinError(error)
    return buffer.raw[:count.value]


def write_pipe(stream, data):
    count = w.DWORD()
    handle = msvcrt.get_osfhandle(stream.fileno())
    checked(write_file(handle, bytes(data), len(data), c.byref(count), None))
    return count.value


class Job:
    def __enter__(self):
        self.handle = checked(create_job(None, None))
        try:
            limits = Limits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway permissions.
            checked(set_job(self.handle, 9, c.byref(limits), c.sizeof(limits)))
        except OSError:
            close_handle(self.handle)
            raise
        return self

    def __exit__(self, *_):
        close_handle(self.handle)

    def assign(self, pid):
        process = checked(open_process(0x0101, False, pid))  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        try:
            checked(assign_process(self.handle, process))
        finally:
            close_handle(process)

    def accounting(self):
        state = Accounting()
        checked(query_job(self.handle, 1, c.byref(state), c.sizeof(state), None))
        return state

    def terminate(self):
        checked(terminate_job(self.handle, 124))

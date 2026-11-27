"""Fixed, trusted synthetic actors. Launched only by the Stage 1.4 harness."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading


ACTORS = Path(__file__).resolve()
REQUEST = b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n'
RESPONSE = b'{"jsonrpc":"2.0","id":1,"result":{}}\n'
INITIALIZE = (b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18",'
              b'"capabilities":{},"clientInfo":{"name":"offline-witness","version":"1"}}}\n')
CONTROL = b"stdin_eof\nstdout_finished\n"
READY = b"ready\n"
ACK = b"terminated\n"
FORCED_JOB_EXIT = 124


def owner(handle):
    if os.read(0, 1) != b"K":
        return 6
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    terminate = kernel.TerminateJobObject
    terminate.argtypes = (wintypes.HANDLE, wintypes.UINT)
    terminate.restype = wintypes.BOOL
    if not terminate(handle, FORCED_JOB_EXIT):
        return 7
    os.write(1, ACK)
    threading.Event().wait()


def synthetic(role, variant):
    # Read bytes directly. The control channel is separate from fictional MCP stdout.
    if variant == "blocked":
        os.write(1, READY)
        threading.Event().wait()
    stream = sys.stdin.buffer
    request = stream.readline(512)
    if request != REQUEST:
        return 4
    os.write(1, request if role == "wrapper" else RESPONSE)
    if stream.read(1) != b"":
        return 5
    if variant != "no_control":
        os.write(2, CONTROL)
    return 7 if variant == "nonzero" else 0


def main():
    role, *arguments = sys.argv[1:]
    if role == "descendant":
        threading.Event().wait()
        return 0
    if os.read(0, 1) != b"G":
        return 3
    if role == "owner":
        return owner(int(arguments[0]))
    if role == "legacy":
        wrapper = ACTORS.parents[1] / "stage-1.3.1" / "wrapper.py"
        sys.path.insert(0, str(wrapper.parent))
        sys.argv[:] = [str(wrapper), "treatment", "--record", arguments[0], "--timeout", "30"]
        runpy.run_path(str(wrapper), run_name="__main__")
        return 0
    if role == "descendant_wrapper":
        child = subprocess.Popen([sys.executable, "-I", "-S", "-B", "-W", "error", str(ACTORS), "descendant"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.write(1, READY)
        # A deliberate root exit while its descendant remains in the same job.
        os._exit(0 if os.read(0, 1) == b"X" and child.poll() is None else 9)
    return synthetic(role, arguments[0])


if __name__ == "__main__":
    raise SystemExit(main())

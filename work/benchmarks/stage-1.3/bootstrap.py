"""Private gated child entry point. The first stdin byte is an ownership handshake."""

import os
from pathlib import Path
import runpy
import sys


class ObservedInput:
    def __init__(self, stream, evidence):
        self.stream = stream
        self.evidence = evidence
        self.observed = False

    def observe(self, data, size):
        if data == b"" and size != 0 and not self.observed:
            self.evidence.write(b"observed\n")
            self.evidence.flush()
            self.observed = True
        return data

    def read(self, size=-1):
        return self.observe(self.stream.read(size), size)

    def readline(self, size=-1):
        return self.observe(self.stream.readline(size), size)


def main():
    # Started with -I -S. No fixture code or user site code runs before Job Object assignment.
    if os.read(sys.stdin.fileno(), 1) != b"\x01":
        return 125
    script, marker, *arguments = sys.argv[1:]
    sys.argv[:] = [script, *arguments]
    sys.path.insert(0, str(Path(script).parent))
    with open(marker, "xb", buffering=0) as evidence:
        original = sys.stdin
        raw = getattr(original.buffer, "raw", original.buffer)

        class Stdin:
            buffer = ObservedInput(raw, evidence)

            def __getattr__(self, key):
                return getattr(original, key)

        sys.stdin = Stdin()
        try:
            runpy.run_path(script, run_name="__main__")
        finally:
            sys.stdin = original
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

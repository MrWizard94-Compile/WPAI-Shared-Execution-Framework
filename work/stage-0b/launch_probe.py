"""Windows opt-in fixture launcher with scoped diagnostics and a lifetime cap."""

import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    if len(sys.argv) != 3 or not re.fullmatch(r"[a-z0-9-]{1,40}", sys.argv[2]):
        raise SystemExit("Usage: launch_probe.py RECORD_DIRECTORY RUN_LABEL")
    base = Path(__file__).resolve().parent
    record_dir = Path(sys.argv[1]).resolve()
    if not record_dir.is_relative_to(base) or record_dir == base:
        raise SystemExit("The record directory must be inside the disposable fixture")
    record_dir.mkdir(parents=True, exist_ok=True)
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
    with (record_dir / f"{sys.argv[2]}.wire.jsonl").open("ab", buffering=0) as diagnostics:
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-B", str(base / "probe.py")],
                cwd=base, env=env, stderr=diagnostics, timeout=60, check=False,
            )
            return completed.returncode
        except subprocess.TimeoutExpired:
            diagnostics.write(b'{"event":"launcher_timeout","seconds":60}\n')
            return 124


if __name__ == "__main__":
    raise SystemExit(main())

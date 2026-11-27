"""Supervise the pinned local synthetic MCP fixture; stdout carries only MCP."""

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from evidence import IDENTITIES, is_run_id, verify_inputs
from supervisor import Limits, forward


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "stage-1.2"))
from benchmark import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("control", "treatment"))
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--private-stderr", type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--run-id", default=None, help="Optional opaque 32-digit lowercase hexadecimal ID")
    args = parser.parse_args()
    run_id = uuid4().hex if args.run_id is None else args.run_id
    if not is_run_id(run_id):
        parser.error("Expected a 32-digit lowercase hexadecimal run ID")
    if args.private_stderr is not None and args.record.resolve() == args.private_stderr.resolve():
        parser.error("The public record and private diagnostic must have distinct paths")
    verify_inputs()
    with TemporaryDirectory(prefix="wpai-synthetic-") as directory:
        trial = Path(directory) / "trial"
        script = prepare(trial, args.arm)
        incoming = getattr(sys.stdin.buffer, "raw", sys.stdin.buffer)
        outgoing = getattr(sys.stdout.buffer, "raw", sys.stdout.buffer)
        record, stderr = forward(incoming, outgoing, script, (args.arm, str(trial / "trace.jsonl")),
                                 limits=Limits(timeout=args.timeout))
    record.update(run_id=run_id, arm=args.arm, fixture_identities=IDENTITIES)
    if args.private_stderr is not None:
        with args.private_stderr.open("xb") as stream:
            stream.write(stderr)
    with args.record.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, indent=2) + "\n")
    return int(not record["lifecycle_valid"])


if __name__ == "__main__":
    raise SystemExit(main())

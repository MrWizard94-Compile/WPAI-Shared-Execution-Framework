"""Prepare the pinned synthetic benchmark and score an agent answer without inference."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
from zipfile import ZipFile


BENCH = Path(__file__).resolve().parent
ARCHIVE = BENCH.parents[2] / "outputs" / "wpai-exec-stage-1.1.zip"
PACKAGE_SHA = "9063cd629145fee025a6330dd969a6bb608bc2571cca72dde5860947652a3686"
LIMIT = 48 * 1024


def object_pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate member")
        result[name] = value
    return result


def invalid_number(_):
    raise ValueError("nonfinite number")


def parse(data):
    return json.loads(data, object_pairs_hook=object_pairs, parse_constant=invalid_number)


def exact(value, expected):
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return value.keys() == expected.keys() and all(exact(value[key], item) for key, item in expected.items())
    if isinstance(expected, list):
        return len(value) == len(expected) and all(exact(item, wanted) for item, wanted in zip(value, expected))
    return value == expected


def score(answer, expected):
    if isinstance(answer, str):
        answer = answer.encode("utf-8")
    try:
        if len(answer) > LIMIT:
            raise ValueError("response size limit")
        decoded = parse(answer)
    except (ValueError, RecursionError):
        return {"valid_json": False, "passed": False, "exact_fields": 0,
                "fields": dict.fromkeys(expected["facts"], "no_valid_json")}
    answer_fields = decoded.get("facts") if isinstance(decoded, dict) else None
    if not isinstance(answer_fields, dict):
        answer_fields = {}
    expected_fields = expected["facts"]
    fields = {key: ("missing" if key not in answer_fields else
                    "exact" if exact(answer_fields[key], value) else "altered")
              for key, value in expected_fields.items()}
    extra_count = len(answer_fields.keys() - expected_fields.keys())
    exact_count = sum(state == "exact" for state in fields.values())
    return {"valid_json": True, "passed": exact(decoded, expected), "exact_fields": exact_count,
            "extra_field_count": extra_count, "fields": fields}


def prompt(arm):
    return (BENCH / "task.txt").read_text(encoding="utf-8").replace(
        "{arm_instruction}", (BENCH / f"{arm}.txt").read_text(encoding="utf-8").strip())


def prepare(path, arm):
    if sha256(ARCHIVE.read_bytes()).hexdigest() != PACKAGE_SHA:
        raise ValueError("Stage 1.1 ZIP identity mismatch")
    with ZipFile(ARCHIVE) as z:
        if z.testzip() is not None:
            raise ValueError("Stage 1.1 ZIP integrity failure")
        items = {name: z.read("wpai-exec/" + name) for name in ("wpai_exec.py", "repo_health.py")}
        manifest = dict(row.split(maxsplit=1)[::-1] for row in z.read("wpai-exec/MANIFEST.sha256").decode().splitlines())
        if any(sha256(z.read("wpai-exec/" + name)).hexdigest() != digest for name, digest in manifest.items()):
            raise ValueError("Stage 1.1 manifest mismatch")
    path.mkdir()
    source = path / "server"
    source.mkdir()
    for name, data in items.items():
        (source / name).write_bytes(data)
    for name in ("ground_truth.json", "server.py"):
        shutil.copyfile(BENCH / name, source / name)
    (path / "workspace").mkdir()
    (path / "prompt.txt").write_bytes(prompt(arm).encode())
    return source / "server.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_subparsers(dest="mode", required=True)
    p = mode.add_parser("prepare")
    p.add_argument("directory", type=Path)
    p.add_argument("arm", choices=("control", "treatment"))
    p = mode.add_parser("score")
    p.add_argument("answer", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.directory, args.arm)
    else:
        result = score(args.answer.read_bytes(), parse((BENCH / "ground_truth.json").read_bytes()))
        print(json.dumps(result))
        return int(not result["passed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

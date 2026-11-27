"""Build the Stage 1.1 distribution from a repository checkout."""

import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo


SOURCE = Path(__file__).resolve().parent
REPOSITORY = SOURCE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    members = {name: (SOURCE / name).read_bytes() for name in ("README.md", "repo_health.py", "wpai_exec.py")}
    members["W1-objective.txt"] = (REPOSITORY / "outputs" / "W1-objective.txt").read_bytes()
    for path in sorted((SOURCE / "tests").glob("test_*.py")):
        members[f"tests/{path.name}"] = path.read_bytes()
    members["MANIFEST.sha256"] = "".join(
        f"{sha256(content).hexdigest()}  {name}\n" for name, content in sorted(members.items())
    ).encode("ascii")

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        for name, content in sorted(members.items()):
            info = ZipInfo(f"wpai-exec/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    data = output.getvalue()
    args.output.write_bytes(data)
    print(sha256(data).hexdigest())


if __name__ == "__main__":
    main()

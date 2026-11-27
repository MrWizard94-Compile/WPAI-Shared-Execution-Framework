"""Compare an authorized original archive with the recorded public archive without emitting path values."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from zipfile import ZipFile


MEMBER = "records/grok.json"
ORIGINAL = "b59081f4feab80c7a0c4eee1f582b0108c3815dec7c4a3a22fddcde2a56a3439"
PUBLISHED = "5b960e0eff88baefcd0623ab0890f9db226be712b8d6a475631e3371536747dc"


def verify(original, published):
    assert sha256(original.read_bytes()).hexdigest() == ORIGINAL
    assert sha256(published.read_bytes()).hexdigest() == PUBLISHED
    account = Path(os.environ["USERPROFILE"]).name
    pattern = re.compile(rf"(?i)\b{re.escape(account)}\b")
    with ZipFile(original) as before, ZipFile(published) as after:
        raw = before.read(MEMBER).decode("utf-8")
        public = after.read(MEMBER).decode("utf-8")
    replaced, count = pattern.subn("LOCAL_USER", raw)
    assert count == 7 and replaced == public and not pattern.search(public)
    return {"member": MEMBER, "local_profile_path_matches": count, "published_unredacted_matches": 0,
            "published_bytes_match_path_substitution": True, "historical_sources_unchanged": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("published", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.original, args.published)))

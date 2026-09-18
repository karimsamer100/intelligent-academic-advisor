#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import tempfile
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the Academic Data Foundation into this project")
    parser.add_argument("zip_path", type=Path, help="Academic_Data_Foundation_SUBMISSION_READY.zip")
    parser.add_argument("--target", type=Path, default=Path("data/academic_foundation"))
    args = parser.parse_args()

    if not args.zip_path.exists():
        raise SystemExit(f"ZIP not found: {args.zip_path}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(args.zip_path) as zf:
            zf.extractall(tmp_path)
        matches = [p for p in tmp_path.rglob("data-foundation-submission") if p.is_dir()]
        if len(matches) != 1:
            raise SystemExit(f"Expected one data-foundation-submission directory, found {len(matches)}")
        source = matches[0]
        if args.target.exists():
            shutil.rmtree(args.target)
        args.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, args.target)

    registry = args.target / "rag" / "source_registry.json"
    if not registry.exists():
        raise SystemExit(f"Installation incomplete: missing {registry}")
    print(f"Academic Data Foundation installed at: {args.target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

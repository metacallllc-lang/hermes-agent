"""Keep every native Windows journey while isolating fork runner disk usage."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path("tests/e2e/core/windows_update")
    files = sorted(root.glob("test_*.py"))
    assert files and sum(p.name == "test_crash_cells.py" for p in files) == 1
    journeys = [
        {"name": p.stem, "path": p.as_posix(), "crash": p.name == "test_crash_cells.py"}
        for p in files
    ]
    if args.repository == "NousResearch/hermes-agent":
        journeys = [{"name": "all", "path": root.as_posix() + "/", "crash": True}]
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write("journeys=" + json.dumps(journeys, separators=(",", ":")) + "\n")
    print(f"Selected {len(journeys)} runner(s), covering all {len(files)} Windows journey files")


if __name__ == "__main__":
    main()

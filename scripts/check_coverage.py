#!/usr/bin/env python3
"""Fail (exit 1) when coverage of a gated area of services/api is below the floor.

Reads the JSON report written by `pytest --cov=hwai --cov-report=json:coverage.json` and
aggregates statements per area (all files under hand/, page/, layout/, safety/, and export.py).
Nothing is excluded: the numbers are plain covered/total statements as measured by coverage.py.
Usage: check_coverage.py [coverage.json] [--floor 80]
"""

import argparse
import json
import sys
from pathlib import Path

AREAS = ("hand/", "page/", "layout/", "safety/", "export.py")
DEFAULT_FLOOR = 80.0


def area_of(path: str) -> str | None:
    norm = path.replace("\\", "/")
    for area in AREAS:
        if f"hwai/{area}" in norm or (
            area.endswith(".py") and norm.endswith(f"hwai/{area}")
        ):
            return area
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", nargs="?", default="coverage.json")
    parser.add_argument("--floor", type=float, default=DEFAULT_FLOOR)
    args = parser.parse_args()
    report = Path(args.report)
    if not report.is_file():
        print(f"coverage report not found: {report}", file=sys.stderr)
        return 1
    files = json.loads(report.read_text())["files"]
    totals: dict[str, list[int]] = {a: [0, 0] for a in AREAS}  # [covered, statements]
    for path, data in files.items():
        area = area_of(path)
        if area is not None:
            totals[area][0] += data["summary"]["covered_lines"]
            totals[area][1] += data["summary"]["num_statements"]
    failed = False
    for area, (covered, total) in totals.items():
        if total == 0:
            print(
                f"FAIL {area:<10} no statements measured (is the area missing from the report?)"
            )
            failed = True
            continue
        pct = 100.0 * covered / total
        ok = pct >= args.floor
        failed |= not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} {area:<10} {pct:5.1f}%  ({covered}/{total})  floor {args.floor:.0f}%"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

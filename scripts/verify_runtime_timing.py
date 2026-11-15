#!/usr/bin/env python3
"""Fail closed on missing or negative routed setup/hold timing evidence."""
import argparse
from pathlib import Path
import re


def verify_report(path):
    text = Path(path).read_text()
    if "Design State : Physopt postRoute" not in text:
        raise ValueError("expected actual post-route timing summary")
    row = re.search(r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)", text, re.MULTILINE)
    if row is None:
        raise ValueError("missing setup/hold endpoint summary")
    wns, _, setup_failures, setup_total, whs, _, hold_failures, hold_total = row.groups()
    if min(int(setup_total), int(hold_total)) == 0:
        raise ValueError("empty timing coverage")
    if float(wns) < 0 or float(whs) < 0 or int(setup_failures) or int(hold_failures):
        raise ValueError(f"routed timing fails: WNS={wns} ns WHS={whs} ns setup_failures={setup_failures} hold_failures={hold_failures}")
    return f"PASS routed timing WNS={wns} ns WHS={whs} ns"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        print(verify_report(args.report))
    except ValueError as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()

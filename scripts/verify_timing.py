"""Verify setup and hold timing closure in a Vivado post-route timing summary report.

Reads a Vivado `timing_summary.rpt` file and prints a `PASS` line with WNS/WHS,
or exits with status 1 if the report is not post-route, has zero endpoint
coverage, negative slack, or any failing endpoints.

Usage:
    python3 scripts/verify_timing.py <path/to/timing_summary.rpt>
"""

import argparse
import re
from pathlib import Path


def verify_report(path):
    """Validate a Vivado post-route timing report and return a PASS summary with WNS and WHS.

    Raises ValueError if the post-route marker or summary row is missing,
    endpoint counts are zero, either slack is negative, or any endpoint fails.
    """
    text = Path(path).read_text()
    if "Design State : Physopt postRoute" not in text:
        raise ValueError("expected actual post-route timing summary")
    row = re.search(
        r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)",
        text,
        re.MULTILINE,
    )
    if row is None:
        raise ValueError("missing setup/hold endpoint summary")
    wns, _, setup_failures, setup_total, whs, _, hold_failures, hold_total = (
        row.groups()
    )
    if min(int(setup_total), int(hold_total)) == 0:
        raise ValueError("empty timing coverage")
    if float(wns) < 0 or float(whs) < 0 or int(setup_failures) or int(hold_failures):
        raise ValueError(
            f"routed timing fails: WNS={wns} ns WHS={whs} ns setup_failures={setup_failures} hold_failures={hold_failures}"
        )
    return f"PASS routed timing WNS={wns} ns WHS={whs} ns"


def main():
    """Parse the report path from CLI arguments and exit 1 if timing validation fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        print(verify_report(args.report))
    except ValueError as error:
        parser.exit(1, f"FAIL: {error}\n")


if __name__ == "__main__":
    main()

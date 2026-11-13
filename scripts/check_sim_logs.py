"""Reject xsim logs without a PASS marker or containing an HDL fatal."""
from pathlib import Path
import sys

if len(sys.argv) < 2:
    raise SystemExit('usage: python scripts/check_sim_logs.py LOG [LOG ...]')
for name in sys.argv[1:]:
    text = Path(name).read_text()
    if 'PASS ' not in text or 'Fatal:' in text or 'FATAL' in text:
        raise SystemExit(f'{name}: missing PASS or HDL fatal')
    print(f'PASS validated {name}')

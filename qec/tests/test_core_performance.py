"""RTL simulation regression tests checking cycle budgets on archived surface-code shots."""

import csv
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "qec/surface/results/runtime-board-20261115"
NAMES = ("memory-d3-z-r3", "memory-d3-x-r5", "memory-d5-z-r3")


@pytest.fixture(scope="module")
def measured_corpus():
    """Simulate archived board shots in Vivado and return paired baseline and RTL cycle measurements."""
    vivado = Path(
        os.environ.get("VIVADO_BIN", "/home/toastcheng/amd/2025.2/Vivado/bin")
    )
    if not all((vivado / tool).is_file() for tool in ("xvlog", "xelab", "xsim")):
        pytest.skip("real Vivado simulator unavailable; no software timing substitute")
    tag = uuid.uuid4().hex[:12]
    vectors = ROOT / f"build/perf-vectors-{tag}.txt"
    vectors.parent.mkdir(exist_ok=True)
    records = [str(len(NAMES))]
    archived = []
    for name in NAMES:
        graph = json.loads((ARCHIVE / f"{name}.json").read_text())
        shots = json.loads((ARCHIVE / f"{name}-shots.json").read_text())
        archived.append(shots)
        counts = graph["counts"]
        records.append(
            f"{counts['detectors']} {counts['edges']} {counts['observables']} {len(shots)}"
        )
        records.extend(f"{a} {b} {mask:08x}" for a, b, mask in graph["edges"])
        records.extend(f"{r['syndrome']:x} {r['prediction']:08x} 0" for r in shots)
    vectors.write_text("\n".join(records) + "\n")
    build = ROOT / f"build/sim/perf-test-{tag}"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/simulate.py",
            "--build-dir",
            str(build),
            "--vivado-bin",
            str(vivado),
            "--vectors",
            str(vectors),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = list(csv.DictReader((build / "profile.csv").open()))
    measured = [[r for r in rows if int(r["graph"]) == g] for g in range(len(NAMES))]
    for before, after in zip(archived, measured):
        assert len(before) == len(after) == 128
        for b, a in zip(before, after):
            assert int(a["syndrome"], 16) == b["syndrome"]
            assert int(a["prediction"], 16) == b["prediction"]
            assert int(a["error"]) == 0
            assert sum(int(a[k]) for k in list(a)[6:]) == int(a["cycles"])
    print(f"Independent RTL edge measurements: {build}")
    return archived, measured


def test_nonempty_serial_scan_budget(measured_corpus):
    """Verify that nonempty syndromes use at least 15% fewer total cycles than the archived baseline."""
    archived, measured = measured_corpus
    for name, before, after in zip(NAMES, archived, measured):
        baseline = sum(r["cycles"] for r in before if r["syndrome"])
        optimized = sum(int(r["cycles"]) for r in after if int(r["syndrome"], 16))
        assert optimized <= 0.85 * baseline, (name, optimized, baseline)


def test_valid_empty_shot_completes_in_one_clock(measured_corpus):
    """Verify that every all-zero syndrome finishes in exactly 1 clock cycle."""
    _, measured = measured_corpus
    empty = [r for rows in measured for r in rows if int(r["syndrome"], 16) == 0]
    assert empty
    assert {int(r["cycles"]) for r in empty} == {1}

"""Vivado RTL simulation tests for the decoder core, cycle counter, and mailbox bridge."""

import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIVADO_BIN = Path(
    os.environ.get("VIVADO_BIN", "/home/toastcheng/amd/2025.2/Vivado/bin")
)


class RtlTests(unittest.TestCase):
    """Execute hardware testbenches in Vivado xsim when the toolchain is available."""
    def run_bench(self, bench):
        """Run one RTL bench in an isolated build directory, skipping if Vivado tools are missing."""
        if not all(
            (VIVADO_BIN / tool).is_file() for tool in ("xvlog", "xelab", "xsim")
        ):
            self.skipTest(
                "real Vivado simulator is not installed; no software RTL substitute"
            )
        build = ROOT / "build" / f"sim/test-{bench}-{uuid.uuid4().hex[:12]}"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/simulate.py"),
                "--bench",
                bench,
                "--build-dir",
                str(build),
                "--vivado-bin",
                str(VIVADO_BIN),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"PASS qec {bench}", result.stdout)
        print(f"{bench}: {build}")

    def test_core_matches_reference_across_qec_graphs(self):
        """Decoder core RTL predictions match the software reference across the QEC graph suite."""
        self.run_bench("core")

    def test_mailbox_cycles_cross_16_bit_boundary(self):
        """Mailbox cycle counter reports counts accurately past the 16-bit boundary (> 65535)."""
        self.run_bench("counter")

    def test_mailbox_rejects_invalid_then_recovers(self):
        """Mailbox bridge rejects an invalid transaction and still processes the next valid one."""
        self.run_bench("bridge")


if __name__ == "__main__":
    unittest.main()

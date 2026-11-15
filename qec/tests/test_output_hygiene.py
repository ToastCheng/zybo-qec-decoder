"""Keep generated files under build/."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tool_caches_are_configured_under_build():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["tool"]["pytest"]["ini_options"]["cache_dir"] == "build/cache/pytest"
    assert config["tool"]["ruff"]["cache-dir"] == "build/cache/ruff"


def test_pytest_does_not_create_a_root_cache(tmp_path):
    test = tmp_path / "test_smoke.py"
    test.write_text("def test_ok():\n    assert True\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(ROOT / "pyproject.toml"),
            str(test),
            "-q",
        ],
        cwd=ROOT,
        check=False,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (ROOT / "build/cache/pytest").is_dir()
    assert not (ROOT / ".pytest_cache").exists()


def test_fpga_tools_run_from_build_with_explicit_logs():
    result = subprocess.run(
        ["make", "-n", "build", "firmware"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "build/tools" in result.stdout
    assert "-log " in result.stdout and "-journal " in result.stdout
    assert "fpga/scripts/build.tcl" in result.stdout
    assert "fpga/vitis/build.py" in result.stdout


def test_project_root_has_no_generated_tool_output():
    forbidden = {".pytest_cache", ".ruff_cache", ".Xil", "xsim.dir", "clockInfo.txt"}
    generated = [
        p.name
        for p in ROOT.iterdir()
        if p.name in forbidden
        or (p.is_file() and p.suffix in {".log", ".jou", ".pb", ".str", ".wdb", ".vcd"})
    ]
    assert generated == [], generated

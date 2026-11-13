"""Standalone build entry points must not depend on the tutorial repository."""
from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('app', ['qec', 'surface'])
def test_firmware_entry_point_reports_its_own_missing_xsa(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, 'vitis', SimpleNamespace())
    with pytest.raises(SystemExit, match=f'build/{app}_soc.xsa not found'):
        runpy.run_path(str(ROOT / f'vitis/{app}/build_app.py'), run_name='__main__')


def test_soc_build_accepts_board_repository_and_uses_its_own_root(tmp_path, monkeypatch):
    boards = tmp_path / 'boards'
    boards.mkdir()
    monkeypatch.setenv('QEC_BOARD_REPO', str(boards))
    harness = tmp_path / 'preflight.tcl'
    harness.write_text('''
proc set_param {key value} {if {$key eq "board.repoPaths"} {puts "BOARD_REPO=$value"}}
proc create_project {args} {puts "BUILD_ROOT=[pwd]"; puts "TOP=$::top"; exit 0}
set argv {}
source {%s}
''' % (ROOT / 'scripts/build_soc.tcl'))
    run = subprocess.run(['tclsh', str(harness)], cwd=tmp_path, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert f'BUILD_ROOT={ROOT}' in run.stdout
    assert f'BOARD_REPO={boards}' in run.stdout
    assert 'TOP=top_surface_soc' in run.stdout


def test_makefile_defaults_to_surface_and_contains_no_tutorial_targets():
    assert (ROOT / 'Makefile').is_file(), 'standalone Makefile is missing'
    text = (ROOT / 'Makefile').read_text()
    assert 'SOC_TOP ?= top_surface_soc' in text
    assert 'APP ?= surface' in text
    assert 'top_hello' not in text and 'ps_hello' not in text


@pytest.mark.parametrize('contents,code', [('PASS bridge\n', 0), ('no result\n', 1),
                                         ('PASS bridge\nFatal: failure\n', 1)])
def test_sim_log_checker_rejects_missing_pass_and_hdl_fatal(tmp_path, contents, code):
    log = tmp_path / 'run.log'
    log.write_text(contents)
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/check_sim_logs.py'), str(log)],
                         text=True, capture_output=True)
    assert run.returncode == code, run.stderr


def test_surface_simulation_uses_selected_tool_directory(tmp_path, monkeypatch):
    # Minimal executables test tool discovery only, NOT RTL correctness.
    tools = tmp_path / 'tools'
    tools.mkdir()
    marker = tmp_path / 'invoked'
    for name in ('xvlog', 'xelab', 'xsim'):
        tool = tools / name
        tool.write_text(f'#!/bin/sh\nprintf "{name}\\n" >> "{marker}"\nprintf "PASS algorithmic surface\\n"\n')
        tool.chmod(0o755)
    monkeypatch.setenv('VIVADO_BIN', str(tools))
    import shutil
    sample = tmp_path / 'project/qec/surface'
    sample.mkdir(parents=True)
    for name in ('sim.py', 'decoder.py'):
        shutil.copy2(ROOT / 'qec/surface' / name, sample / name)
    run = subprocess.run([sys.executable, str(sample / 'sim.py'), '--shots', '1'],
                         cwd=tmp_path, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert marker.exists(), 'surface simulation ignored VIVADO_BIN'
    assert marker.read_text().splitlines() == ['xvlog', 'xelab', 'xsim']

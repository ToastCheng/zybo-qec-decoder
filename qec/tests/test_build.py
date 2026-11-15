"""Test build paths and failure handling with Tcl and Vitis command doubles."""

import os
import runpy
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "fpga/scripts/build.tcl"


def run_build(
    tmp_path,
    *,
    setup="0.12",
    hold="0.03",
    output=None,
    progress="100%",
    capacities=(64, 256, 8),
):
    output = output or tmp_path / "image"
    harness = tmp_path / "harness.tcl"
    harness.write_text(r"""
proc unknown {command args} {
    puts "CALL $command $args"
    switch -- $command {
        get_property {
            if {[lindex $args 0] eq "PROGRESS"} {return $::progress}
            if {[lindex $args 0] eq "SLACK"} {
                if {[string match *min* [lindex $args 1]]} {return $::hold}
                return $::setup
            }
        }
        get_timing_paths {return [list [join $args]]}
        make_wrapper {
            set path [file join $::output vivado_qec_soc qec_soc.gen sources_1 bd system hdl system_wrapper.v]
            file mkdir [file dirname $path]
            close [open $path w]
            return [list $path]
        }
        wait_on_run {
            set path [file join $::output vivado_qec_soc qec_soc.runs impl_1 top_qec_soc.bit]
            file mkdir [file dirname $path]
            close [open $path w]
        }
        write_hw_platform {close [open [lindex $args end] w]}
        default {return [lindex $args end]}
    }
}
set output [lindex $argv 1]
set setup [lindex $argv 2]
set hold [lindex $argv 3]
set progress [lindex $argv 4]
set build [lindex $argv 0]
set argv [linsert [lrange $argv 5 end] 0 $output]
source $build
""")
    return subprocess.run(
        [
            "tclsh",
            str(harness),
            str(BUILD),
            str(output),
            setup,
            hold,
            progress,
            *map(str, capacities),
        ],
        check=False,
        cwd=tmp_path,
        text=True,
        capture_output=True,
    )


def test_qec_build_isolated_sources_reports_and_export(tmp_path):
    result = run_build(tmp_path)
    assert result.returncode == 0, result.stderr
    log = result.stdout
    assert "xc7z010clg400-1" in log
    assert "Performance_ExplorePostRoutePhysOpt" in log
    for source in [
        "qec_decoder.sv",
        "ps_bridge.sv",
        "top_qec_soc.sv",
    ]:
        assert (
            str(
                ROOT
                / ("fpga/rtl/top" if source.startswith("top_") else "fpga/rtl/common")
                / source
            )
            in log
        )
    assert "MAX_DETECTORS=64 MAX_EDGES=256 MAX_OBSERVABLES=8" in log
    assert "CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ 100.000000" in log
    for command in ["report_utilization", "report_timing_summary", "report_drc"]:
        assert f"CALL {command}" in log
    assert "-delay_type max" in log and "-delay_type min" in log
    assert "surface_decoder.sv" not in log.replace("qec_decoder.sv", "")
    assert "lut.mem" not in log and "SEVERITY" not in log
    assert (tmp_path / "image/qec_soc.xsa").is_file()
    assert (tmp_path / "image/qec_soc.bit").is_file()


@pytest.mark.parametrize(
    "setup,hold,progress",
    [
        ("-0.1", "0.1", "100%"),
        ("0.1", "-0.1", "100%"),
        ("0.1", "0.1", "75%"),
        ("", "0.1", "100%"),
    ],
)
def test_failed_or_missing_timing_never_exports(tmp_path, setup, hold, progress):
    result = run_build(tmp_path, setup=setup, hold=hold, progress=progress)
    assert result.returncode != 0
    assert "CALL write_hw_platform" not in result.stdout
    assert not (tmp_path / "image/qec_soc.bit").exists()


def test_existing_directory_is_not_overwritten(tmp_path):
    image = tmp_path / "existing"
    image.mkdir()
    sentinel = image / "surface_soc.bit"
    sentinel.write_bytes(b"valuable")
    result = run_build(tmp_path, output=image)
    assert result.returncode != 0
    assert "CALL create_project" not in result.stdout
    assert sentinel.read_bytes() == b"valuable"


def test_top_forwards_capacity_clock_reset_and_mailbox():
    top = (ROOT / "fpga/rtl/top/top_qec_soc.sv").read_text()
    for parameter, default in [
        ("MAX_DETECTORS", 128),
        ("MAX_EDGES", 512),
        ("MAX_OBSERVABLES", 32),
    ]:
        assert f"parameter integer {parameter} = {default}" in top
        assert f".{parameter}({parameter})" in top
    assert "ps_bridge #(" in top
    for connection in [
        ".clk(clk)",
        ".rst(!resetn)",
        ".ctrl(ctrl)",
        ".status(status)",
        ".FCLK_CLK0_0(clk)",
        ".peripheral_aresetn_0(resetn)",
    ]:
        assert connection in top
    assert "defparam" not in top and "ROM" not in top
    constraints = (ROOT / "fpga/constraints/top_qec_soc.xdc").read_text()
    for pin in ["M14", "M15", "G14", "D18"]:
        assert pin in constraints
    assert "create_clock" not in constraints


def fake_vitis(monkeypatch, *, export_platform=True, export_elf=True):
    events = []

    class Component:
        def __init__(self, name, client):
            self.name = name
            self.client = client

        def build(self):
            events.append(("build", self.name))
            base = self.client.workspace / self.name
            if self.name == "qec_platform" and export_platform:
                target = base / "export/qec_platform/qec_platform.xpfm"
            elif self.name == "qec_app" and export_elf:
                target = base / "build/qec_app.elf"
            else:
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()

        def remove_files(self, **kwargs):
            events.append(("remove", kwargs))

        def import_files(self, **kwargs):
            events.append(("import", kwargs))

    class Client:
        def set_workspace(self, path):
            self.workspace = Path(path)
            events.append(("workspace", path))

        def create_platform_component(self, **kwargs):
            events.append(("platform", kwargs))
            return Component(kwargs["name"], self)

        def create_app_component(self, **kwargs):
            events.append(("app", kwargs))
            config = self.workspace / kwargs["name"] / "src/UserConfig.cmake"
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text('set(USER_COMPILE_SOURCES\n"helloworld.c"\n"main.c"\n)\n')
            return Component(kwargs["name"], self)

    monkeypatch.setitem(
        sys.modules, "vitis", types.SimpleNamespace(create_client=lambda: Client())
    )
    return events


def test_vitis_qec_build_uses_isolated_root_relative_paths(tmp_path, monkeypatch):
    image = tmp_path / "image"
    image.mkdir()
    (image / "qec_soc.xsa").touch()
    events = fake_vitis(monkeypatch)
    monkeypatch.chdir(tmp_path)
    # Resolve relative image paths against the repository, regardless of cwd.
    monkeypatch.setenv("QEC_IMAGE_DIR", os.path.relpath(image, ROOT))
    runpy.run_path(str(ROOT / "fpga/vitis/build.py"), run_name="__main__")
    assert ("workspace", str(image / "vitis_ws")) in events
    platform = next(data for event, data in events if event == "platform")
    assert platform == {
        "name": "qec_platform",
        "hw_design": str(image / "qec_soc.xsa"),
        "os": "standalone",
        "cpu": "ps7_cortexa9_0",
    }
    app = next(data for event, data in events if event == "app")
    assert app["name"] == "qec_app"
    assert app["domain"] == "standalone_ps7_cortexa9_0"
    assert (
        "import",
        {"from_loc": str(ROOT / "fpga/vitis/src"), "dest_dir_in_cmp": "src"},
    ) in events
    config = (image / "vitis_ws/qec_app/src/UserConfig.cmake").read_text()
    assert "helloworld.c" not in config and '"main.c"' in config
    assert events[-1] == ("build", "qec_app")


@pytest.mark.parametrize(
    "capacities", [(0, 256, 8), (64, -1, 8), (64, 256, 33), ("oops", 256, 8)]
)
def test_invalid_capacities_fail_before_creating_project(tmp_path, capacities):
    result = run_build(tmp_path, capacities=capacities)
    assert result.returncode != 0
    assert "Invalid decoder capacity" in result.stderr
    assert "CALL create_project" not in result.stdout


@pytest.mark.parametrize("output", [ROOT, ROOT / "build", ROOT / "vitis", ROOT.parent])
def test_protected_output_directories_are_rejected(tmp_path, output):
    result = run_build(tmp_path, output=output)
    assert result.returncode != 0
    assert "CALL create_project" not in result.stdout


def test_existing_empty_output_directory_is_allowed(tmp_path):
    output = tmp_path / "image"
    output.mkdir()
    assert run_build(tmp_path, output=output).returncode == 0


@pytest.mark.parametrize(
    "export_platform,export_elf,error",
    [(False, True, "platform export"), (True, False, "QEC ELF")],
)
def test_vitis_missing_exports_cannot_report_success(
    tmp_path, monkeypatch, capsys, export_platform, export_elf, error
):
    (tmp_path / "qec_soc.xsa").touch()
    fake_vitis(monkeypatch, export_platform=export_platform, export_elf=export_elf)
    monkeypatch.setenv("QEC_IMAGE_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match=error):
        runpy.run_path(str(ROOT / "fpga/vitis/build.py"), run_name="__main__")
    assert "Build complete" not in capsys.readouterr().out


@pytest.mark.parametrize("existing_workspace", [False, True])
def test_vitis_preflight_does_not_touch_vendor_on_invalid_input(
    tmp_path, monkeypatch, existing_workspace
):
    if existing_workspace:
        (tmp_path / "qec_soc.xsa").touch()
        workspace = tmp_path / "vitis_ws"
        workspace.mkdir()
        (workspace / "valuable.txt").write_text("keep")
    events = fake_vitis(monkeypatch)
    monkeypatch.setenv("QEC_IMAGE_DIR", str(tmp_path))
    with pytest.raises(
        RuntimeError,
        match="Refusing nonempty workspace" if existing_workspace else "not found",
    ):
        runpy.run_path(str(ROOT / "fpga/vitis/build.py"), run_name="__main__")
    assert events == []


def test_board_repository_relative_path_resolves_from_root(tmp_path, monkeypatch):
    board_repo = tmp_path / "boards"
    board_repo.mkdir()
    monkeypatch.setenv("QEC_BOARD_REPO", os.path.relpath(board_repo, ROOT))
    result = run_build(tmp_path)
    assert result.returncode == 0, result.stderr
    assert f"board.repoPaths {board_repo}" in result.stdout


@pytest.mark.parametrize("directory", [ROOT, ROOT / "fpga", ROOT / "build"])
def test_simulator_rejects_outputs_outside_private_sim_directory(directory):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/simulate.py"),
            "--build-dir",
            str(directory),
            "--vivado-bin",
            "/missing/tools",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "build/sim" in result.stderr
    assert "FileNotFoundError" not in result.stderr


def test_status_reads_configuration_without_programming(tmp_path):
    harness = tmp_path / "status.tcl"
    harness.write_text(
        'proc unknown {command args} {puts "CALL $command $args"; return device}\n'
        f"source {{{ROOT / 'fpga/scripts/status.tcl'}}}\n"
    )
    result = subprocess.run(
        ["tclsh", str(harness)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CALL refresh_hw_device" in result.stdout
    assert "CALL report_property" in result.stdout
    assert "CALL fpga" not in result.stdout
    assert "CALL program_hw_devices" not in result.stdout

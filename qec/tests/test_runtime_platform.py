"""Native BSP doubles exercise the production platform/header and firmware main."""

import os
import runpy
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "vitis/runtime/src"

BSP = r"""
#ifndef TEST_BSP_H
#define TEST_BSP_H
#include <stddef.h>
#include <stdint.h>
#define XPAR_XUARTPS_0_BASEADDR 0xe0001000u
#define XPAR_UART1_BASEADDR 0xe0001000u
#define XUARTPS_OPER_MODE_NORMAL 0u
#define XUARTPS_FIFO_OFFSET 0x30u
#define XPAR_CPU_CORE_CLOCK_FREQ_HZ 666666666ULL
/* Generated xtimer_config.h deliberately has no grouping parentheses. */
#define COUNTS_PER_SECOND XPAR_CPU_CORE_CLOCK_FREQ_HZ/2
/* Match the SDT/base-address lookup signatures used by 2025.2. */
typedef uint64_t XTime;
typedef struct { uintptr_t BaseAddress; } XUartPs_Config;
typedef struct { unsigned unused; } XUartPs;
XUartPs_Config *XUartPs_LookupConfig(uintptr_t);
int XUartPs_CfgInitialize(XUartPs *, XUartPs_Config *, uintptr_t);
int XUartPs_SetBaudRate(XUartPs *, uint32_t);
void XUartPs_SetOperMode(XUartPs *, uint8_t);
int XUartPs_IsReceiveData(uintptr_t);
uint32_t XUartPs_ReadReg(uintptr_t, unsigned);
void XUartPs_SendByte(uintptr_t, uint8_t);
int XUartPs_IsTransmitFifoEmpty(uintptr_t);
int XUartPs_IsTransmitActive(uintptr_t);
void XTime_GetTime(XTime *);
void Xil_Out32(uintptr_t, uint32_t);
uint32_t Xil_In32(uintptr_t);
#endif
"""

HARNESS = r"""
#include <assert.h>
#include <setjmp.h>
#include <stdlib.h>
#include <string.h>
#include "bsp.h"
#define main production_main
#include "main.c"
#undef main
static jmp_buf done;
static XTime ticks;
static uint32_t status_word, last_control;
static unsigned control_writes, init_step, tx_polls, active_polls;
static int fail_init, hold_ack, finish_loop;
static uint8_t input[32], output[128];
static size_t input_len, input_pos, output_len;
static XUartPs_Config config = {XPAR_UART1_BASEADDR};
XUartPs_Config *XUartPs_LookupConfig(uintptr_t base) {
    assert(base == XPAR_UART1_BASEADDR);
    assert(init_step++ == 0);
    return fail_init == 1 ? NULL : &config;
}
int XUartPs_CfgInitialize(XUartPs *u, XUartPs_Config *c, uintptr_t base) {
    (void)u; assert(c == &config && base == config.BaseAddress);
    assert(init_step++ == 1); return fail_init == 2;
}
int XUartPs_SetBaudRate(XUartPs *u, uint32_t rate) {
    (void)u; assert(rate == 115200); assert(init_step++ == 2);
    return fail_init == 3;
}
void XUartPs_SetOperMode(XUartPs *u, uint8_t mode) {
    (void)u; assert(mode == XUARTPS_OPER_MODE_NORMAL); assert(init_step++ == 3);
}
int XUartPs_IsReceiveData(uintptr_t base) {
    assert(base == XPAR_UART1_BASEADDR);
    if (finish_loop && input_pos == input_len) longjmp(done, 1);
    return input_pos < input_len;
}
uint32_t XUartPs_ReadReg(uintptr_t base, unsigned offset) {
    assert(base == XPAR_UART1_BASEADDR && offset == XUARTPS_FIFO_OFFSET);
    assert(input_pos < input_len); return input[input_pos++];
}
void XUartPs_SendByte(uintptr_t base, uint8_t byte) {
    assert(base == XPAR_UART1_BASEADDR); assert(output_len < sizeof(output));
    output[output_len++] = byte;
}
int XUartPs_IsTransmitFifoEmpty(uintptr_t base) {
    assert(base == XPAR_UART1_BASEADDR); return ++tx_polls > 2;
}
int XUartPs_IsTransmitActive(uintptr_t base) {
    assert(base == XPAR_UART1_BASEADDR); return ++active_polls < 3;
}
void XTime_GetTime(XTime *t) { *t = ticks; ticks += COUNTS_PER_SECOND / 1000 + 1; }
void Xil_Out32(uintptr_t address, uint32_t value) {
    if (address == 0x41200004u) { assert(value == 0); return; }
    if (address == 0x4120000cu) { assert(value == UINT32_MAX); return; }
    assert(address == 0x41200000u);
    last_control = value; ++control_writes;
    if (!hold_ack) status_word = (value & 0x80000000u) | (value >> 16 & 255u);
}
uint32_t Xil_In32(uintptr_t address) {
    assert(address == 0x41200008u); return status_word;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    if (argv[1][0] == 'f') {
        fail_init = argv[1][1] - '0'; runtime_platform_init(); abort();
    }
    if (!strcmp(argv[1], "main")) {
        input[0] = 0xd4; input[1] = 42; input[2] = 1;
        input[3] = 0; input[4] = 0;
        uint32_t crc = runtime_crc32(input, 5);
        for (unsigned i = 0; i < 4; ++i) input[5+i] = (uint8_t)(crc >> (8*i));
        input_len = 9; finish_loop = 1;
        if (!setjmp(done)) (void)production_main();
        assert(output_len == 69 && output[0] == 0x4d && output[1] == 42);
        assert(output[2] == 0 && output[3] == 60 && output[4] == 0);
        for (unsigned i = 0; i < 15; ++i) assert(get32(output + 5 + 4*i) == i);
        assert(get32(output + 65) == runtime_crc32(output, 65));
        assert(control_writes == 15 && tx_polls > 2 && active_polls >= 3);
        return 0;
    }
    runtime_platform_init();
    assert(init_step == 4 && output_len == 0 && control_writes == 0);
    assert(runtime_platform_read_byte() == -1);
    input[0] = 0; input[1] = 255; input_len = 2;
    assert(runtime_platform_read_byte() == 0);
    assert(runtime_platform_read_byte() == 255);
    assert(runtime_platform_read_byte() == -1);
    const uint8_t bytes[] = {0, 255, 0xd4};
    runtime_platform_emit(NULL, bytes, sizeof(bytes));
    assert(output_len == sizeof(bytes) && !memcmp(output, bytes, sizeof(bytes)));
    assert(tx_polls > 2 && active_polls >= 3);
    ticks = 123456789ULL * (COUNTS_PER_SECOND) + (COUNTS_PER_SECOND) - 1;
    assert(runtime_platform_now_ms(NULL) == (uint32_t)123456789999ULL);
    ticks = 4294967295ULL * (COUNTS_PER_SECOND) / 1000;
    uint32_t before = runtime_platform_now_ms(NULL);
    ticks += COUNTS_PER_SECOND / 100;
    uint32_t after = runtime_platform_now_ms(NULL);
    assert((uint32_t)(after - before) >= 10 && (uint32_t)(after - before) <= 12);
    runtime_gpio g;
    status_word = 0x80000000u;
    runtime_gpio_init(&g, runtime_platform_write_control, runtime_platform_read_status,
                      runtime_platform_now_ms, NULL, 3);
    uint16_t value = 0;
    hold_ack = 1;
    assert(runtime_gpio_mailbox(&g, 6, 0, 0, &value) == 4);
    assert(control_writes == 1 && last_control == 0x06000000u);
    assert(runtime_gpio_mailbox(&g, 8, 0, 0, &value) == 4);
    assert(control_writes == 1); /* No second toggle for an unacknowledged decode. */
    status_word = last_control & 0x80000000u; hold_ack = 0;
    assert(runtime_gpio_mailbox(&g, 7, 2, 0, &value) == 0);
    assert(control_writes == 2 && last_control == 0x87020000u && value == 2);
    return 0;
}
"""


def write_bsp_stubs(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name in [
        "bsp.h",
        "xparameters.h",
        "xil_io.h",
        "xuartps.h",
        "xuartps_hw.h",
        "xiltimer.h",
    ]:
        (directory / name).write_text(BSP if name == "bsp.h" else '#include "bsp.h"\n')


@pytest.fixture
def native_platform(tmp_path):
    write_bsp_stubs(tmp_path)
    harness = tmp_path / "platform.c"
    harness.write_text(HARNESS)
    executable = tmp_path / "platform"
    result = subprocess.run(
        [
            "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-g",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-fno-pie",
            "-no-pie",
            '-DRUNTIME_PLATFORM_HEADER="runtime_platform.h"',
            "-I",
            str(tmp_path),
            "-I",
            str(SOURCE),
            str(harness),
            "-o",
            str(executable),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return executable


@pytest.mark.parametrize("mode", ["platform", "main", "f1", "f2", "f3"])
def test_production_platform_with_native_bsp(native_platform, mode):
    result = subprocess.run(
        [str(native_platform), mode], capture_output=True, text=True
    )
    assert result.returncode == (1 if mode.startswith("f") else 0), result.stderr
    assert result.stdout == "" and result.stderr == ""


def test_builder_rejects_missing_platform_header_before_vendor(tmp_path, monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "runtime_builder", ROOT / "vitis/runtime/build_app.py"
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.delenv("QEC_RUNTIME_OUTPUT_DIR", raising=False)
    source = tmp_path / "vitis/runtime/src"
    source.mkdir(parents=True)
    (source / "main.c").touch()
    image = tmp_path / "build/runtime-image"
    image.mkdir(parents=True)
    (image / "runtime_soc.xsa").touch()
    monkeypatch.setitem(sys.modules, "vitis", None)
    with pytest.raises(RuntimeError, match="runtime_platform.h"):
        builder.main()


def test_builder_selects_real_header_with_cmake_and_keeps_sources(
    tmp_path, monkeypatch
):
    """Fake vendor orchestration, real CMake/compiler; not BSP link/ELF evidence."""
    before = {p: p.read_bytes() for p in SOURCE.iterdir() if p.is_file()}
    image = tmp_path / "image"
    image.mkdir()
    (image / "runtime_soc.xsa").touch()
    events = []

    class Component:
        def __init__(self, name, workspace):
            self.name = name
            self.base = workspace / name

        def build(self):
            events.append(("build", self.name))
            if self.name == "runtime_platform":
                target = self.base / "export/runtime_platform/runtime_platform.xpfm"
            else:
                # CMake consumes the generated UserConfig just as the app does.
                # Object-only compilation avoids claiming a native ELF is ARM firmware.
                write_bsp_stubs(self.base / "bsp")
                (self.base / "CMakeLists.txt").write_text(
                    "cmake_minimum_required(VERSION 3.16)\nproject(native_probe C)\n"
                    "include(src/UserConfig.cmake)\n"
                    "add_library(probe OBJECT src/main.c)\n"
                    "target_include_directories(probe PRIVATE bsp)\n"
                    "target_compile_options(probe PRIVATE -Wall -Wextra -Werror)\n"
                )
                for args in [
                    ["cmake", "-S", str(self.base), "-B", str(self.base / "build")],
                    ["cmake", "--build", str(self.base / "build")],
                ]:
                    result = subprocess.run(args, capture_output=True, text=True)
                    assert result.returncode == 0, result.stdout + result.stderr
                target = self.base / "build/runtime_app.elf"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fake vendor export; not a hardware artifact")

        def remove_files(self, **kwargs):
            assert kwargs == {"files": ["src/helloworld.c"]}

        def import_files(self, **kwargs):
            assert kwargs == {"from_loc": str(SOURCE), "dest_dir_in_cmp": "src"}
            shutil.copytree(SOURCE, self.base / "src", dirs_exist_ok=True)

    class Client:
        def set_workspace(self, path):
            self.workspace = Path(path)

        def create_platform_component(self, **kwargs):
            assert kwargs["hw_design"] == str(image / "runtime_soc.xsa")
            return Component(kwargs["name"], self.workspace)

        def create_app_component(self, **kwargs):
            component = Component(kwargs["name"], self.workspace)
            component.base.joinpath("src").mkdir(parents=True)
            component.base.joinpath("src/UserConfig.cmake").write_text(
                'set(USER_COMPILE_SOURCES\n"helloworld.c"\n"main.c"\n)\n'
            )
            return component

    monkeypatch.setitem(
        sys.modules, "vitis", types.SimpleNamespace(create_client=Client)
    )
    monkeypatch.setenv("QEC_RUNTIME_OUTPUT_DIR", os.path.relpath(image, ROOT))
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(ROOT / "vitis/runtime/build_app.py"), run_name="__main__")
    assert events == [("build", "runtime_platform"), ("build", "runtime_app")]
    assert {p: p.read_bytes() for p in before} == before
    assert (image / "vitis_ws/runtime_app/build/runtime_app.elf").is_file()

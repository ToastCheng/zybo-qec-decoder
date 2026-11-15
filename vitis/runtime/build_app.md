# Runtime standalone firmware builder

`build_app.py` runs under AMD Vitis Unified 2025.2:

```sh
vitis -s /home/toastcheng/dev/zybo-qec-decoder/vitis/runtime/build_app.py
```

The default hardware handoff is repository-relative
`build/runtime-image/runtime_soc.xsa`, produced by
[build_runtime.tcl](../../scripts/build_runtime.md). For a different output:

```sh
QEC_RUNTIME_OUTPUT_DIR=build/runtime-image-next \
    vitis -s /home/toastcheng/dev/zybo-qec-decoder/vitis/runtime/build_app.py
```

Relative image paths resolve from the source repository, not the process working
directory. Absolute external image paths are supported. Root/source-tree and
legacy build-root destinations are refused. `QEC_IMAGE_DIR`, graph headers and
fixed-image workspaces are not read.

## Build sequence

`main()` preflights the XSA, maintained `vitis/runtime/src/main.c` and
`runtime_platform.h`, and an absent
or empty `vitis_ws` directory beneath the chosen image. It refuses nonempty
workspaces rather than deleting components or trusting stale exports.

The Vitis client creates `runtime_platform` with standalone OS on
`ps7_cortexa9_0`, builds it, and requires exactly one exported `.xpfm`. It creates
`runtime_app` in `standalone_ps7_cortexa9_0` using the `hello_world` template,
removes `src/helloworld.c`, and imports only `vitis/runtime/src`. The generated
`UserConfig.cmake` also has the stale quoted `helloworld.c` source line removed;
Vitis can leave that entry after deleting the file. Maintained firmware is never
rewritten or prefixed with fixed graph macros. The generated CMake configuration
selects `RUNTIME_PLATFORM_HEADER=\"runtime_platform.h\"` with escaped C-string
quotes, applying to the copied source without editing either maintained main.c
or the imported main.c. The platform header uses the real 2025.2 xiltimer API.

After application build, exactly one ELF must exist at
`<image>/vitis_ws/runtime_app/build/*.elf` before a completion message is printed.
Missing/ambiguous platform or ELF exports and vendor exceptions fail the build.
A failed workspace is retained for inspection; move/remove only that runtime
workspace explicitly, or select a new matching runtime image directory to retry.
The script does not program or boot a board.

The regression injects a mocked `vitis` module, checks client calls/path resolution
from a foreign directory, inspects generated template cleanup and rejects missing
exports/stale workspaces. This validates Python orchestration, not compilation,
ELF contents or hardware/firmware compatibility. A real Vitis build still needs
the matching runtime XSA. A BSP-only compilation probe may use a no-bitstream
XSA exported from synthesis, but that is not a routed or board-ready image.

The actual Vitis 2025.2 builder was exercised against the synthesized runtime
handoff in `build/runtime-firmware-platform-probe`: it compiled the maintained
main.c/platform header and linked a Cortex-A9 `runtime_app.elf` with xiltimer.
This probe intentionally contains no bitstream; the 100 MHz route acceptance
and matching programmed-board tests remain separate blockers. Vendor-generated
BSP warnings were present; the application compile/link succeeded.

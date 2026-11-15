# Surface firmware builder

[Source](build_app.py). Run `vitis -s vitis/surface/build_app.py` from the repository root using Vitis Unified 2025.2. Top-level statements execute immediately; this is not an import-safe library. The `vitis` module must come from the SDK. The script builds files without programming a board.

## Inputs and flow

The XSA is `build/surface_soc.xsa`, workspace is `build/vitis_ws`, platform is `surface_platform`, app is `surface_app`, and maintained sources are `vitis/surface/src`. No alternate-image environment variable is read.

1. Require the XSA, create a Vitis client and select the workspace.
2. Attempt platform deletion; create/build a standalone platform for `ps7_cortexa9_0` and select the first exported `.xpfm` match.
3. Attempt app deletion and create a `hello_world` app in the standalone domain.
4. Remove `src/helloworld.c` and import maintained source files.
5. Remove the exact `"helloworld.c"` plus newline entry from generated `src/UserConfig.cmake`; SDK deletion alone leaves this stale compile-source reference.
6. Build and print the first `surface_app/build/*.elf` match.

## Failure and recovery

Missing XSA/export/ELF exits explicitly. Other SDK/file/build errors propagate. Delete exceptions are broadly ignored, so cleanup is not guaranteed. A failed run can leave a partial workspace; inspect SDK errors before retrying. Recreating components can discard workspace hand edits. File existence does not prove freshness or compatibility with a loaded bitstream.

```sh
make build_soc
vitis -s vitis/surface/build_app.py
python -m py_compile vitis/surface/build_app.py
cc -std=c11 -Wall -Wextra -Werror qec/surface/test_firmware.c -o "$TMPDIR/test_firmware"
"$TMPDIR/test_firmware"
```

Syntax checking does not invoke Vitis. Native parser tests exclude MMIO/UART and do not establish physical board operation.

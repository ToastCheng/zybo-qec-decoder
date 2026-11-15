# Repetition firmware builder

Run `vitis -s vitis/qec/build_app.py` from the repository root with Vitis Unified 2025.2. This is a top-level build script, not an import-safe library; importing it executes the build. It requires the Vitis Python `vitis` module and an existing `build/qec_soc.xsa` (`make build_soc SOC_TOP=top_qec_soc`). Plain Python is sufficient only for syntax checks.

## Inputs, names and sequence

Constants select workspace `build/vitis_ws`, platform `qec_platform`, application `qec_app`, and absolute source path `vitis/qec/src`. `vitis.create_client()` selects the workspace; old platform deletion is attempted, then `create_platform_component` targets `standalone` on `ps7_cortexa9_0`. The platform is built before discovering its exported `.xpfm` using `glob`. The first match is used without explicit sorting.

The application is deleted/recreated against `standalone_ps7_cortexa9_0` using the `hello_world` template. `remove_files` drops `src/helloworld.c`; `import_files` copies maintained sources into the component's `src`. The script reads generated `UserConfig.cmake` and removes the exact `"helloworld.c"` plus newline reference: removing the file alone leaves a stale `USER_COMPILE_SOURCES` entry that prevents CMake configuration. `app.build()` creates the ELF; a final glob discovers `build/vitis_ws/qec_app/build/*.elf` and prints the first match.

## Failures and reruns

Missing XSA, missing platform export, and missing ELF terminate through explicit `sys.exit` messages. Component-deletion exceptions are swallowed broadly, including failures other than “not found”; later creation/build can still fail. Build, SDK, file I/O and configuration errors otherwise propagate. There is no rollback, retry loop, artifact freshness validation or timeout in this script. Rerunning attempts component replacement; keep any manual workspace edits elsewhere. It writes generated workspace files but does not program a board.

## Commands and verification scope

```sh
make build_soc SOC_TOP=top_qec_soc
vitis -s vitis/qec/build_app.py
python -m py_compile vitis/qec/build_app.py
cc -std=c11 -Wall -Wextra -Werror qec/test_ps_firmware.c -o "$TMPDIR/test_ps_firmware"
"$TMPDIR/test_ps_firmware"
```

Syntax checking does not import Vitis or prove a hardware build. The native C test checks parser semantics independently of SDK availability.

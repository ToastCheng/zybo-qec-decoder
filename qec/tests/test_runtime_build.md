# Runtime build integration tests

`test_runtime_build.py` verifies the new standalone build orchestration without
starting Vivado synthesis or a real Vitis session:

```sh
uv run --with pytest python -m pytest qec/tests/test_runtime_build.py -q
```

Python/pytest and `tclsh` are required. Tests derive the repository root from
their own path, so changing the caller's directory does not change source lookup.

## Tcl execution harness

`run_build()` writes a Tcl harness under pytest's temporary directory and sources
the actual `scripts/build_runtime.tcl`. Only vendor commands are instrumented;
Tcl branches, path handling, file protection, block-design script sourcing and
export ordering execute normally. The shim logs commands, supplies implementation
progress and setup/hold slack, and creates explicitly fake wrapper, private bit,
and XSA fixture files. These are not synthesis results or usable images.

Tests assert the runtime-only source allowlist, Z7-10 part, 100 MHz PS property,
capacity forwarding, performance strategy, report commands and setup/hold checks.
Negative setup/hold, missing slack and incomplete run progress must not export.
Sentinel files prove nonempty old output directories are preserved. Separate
cases cover forbidden directory roots, empty directories, invalid capacities and
repository-relative board-file paths.
The structural top/XDC test checks capacity defaults/forwarding, shared-clock
mailbox/reset wiring and LED pin names; it is not an HDL compiler.

## Mocked Vitis boundary

`fake_vitis()` implements only the client/component methods used by the actual
builder and writes fake platform/ELF exports plus a generated CMake fixture.
The main test runs the builder from a foreign working directory with a relative
runtime-image setting and a poisoned old `QEC_IMAGE_DIR`, then checks standalone
CPU/domain, runtime source imports, isolated workspace/application names and
template cleanup. Other tests ensure missing platform/ELF exports, missing XSA
and stale workspaces cannot be reported as successful builds.

## Evidence limits

The initial missing-build-script, missing-top and missing-Vitis-builder tests
were observed failing before their implementations were added. The tests then
passed against the implemented paths. Mocked tests do not establish IP automation,
RTL elaboration, runtime algorithm correctness, routed capacities/timing, actual
firmware compilation or board operation. Those boundaries require separate real
AMD-tool runs after sibling RTL/firmware are complete; this suite deliberately
never polls for sibling readiness or programs hardware.

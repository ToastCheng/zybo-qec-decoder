# Standalone runtime image build

`build_runtime.tcl` builds the runtime-loadable decoder independently of the old
fixed-image build scripts, graph configuration headers and graph ROMs. AMD
Vivado 2025.2 and the Digilent Zybo Z7-10 board files must be installed. The part
is `xc7z010clg400-1`, board preset `digilentinc.com:zybo-z7-10:part0:1.2`.
`QEC_BOARD_REPO` may select a board-files directory (relative paths resolve from
the repository); otherwise the script checks
an AMD-adjacent board repository, then leaves Vivado's configured search paths.

## Invocation

From any working directory, use an absolute script path:

```sh
vivado -mode batch -source /home/toastcheng/dev/zybo-qec-decoder/scripts/build_runtime.tcl
```

The default output is repository-relative `build/runtime-image`. Optional Tcl
arguments select a new output directory and synthesized capacity ceilings:

```sh
vivado -mode batch -source /home/toastcheng/dev/zybo-qec-decoder/scripts/build_runtime.tcl \
    -tclargs build/runtime-image-next 128 512 32
```

Relative output paths resolve from the repository, not the caller's directory.
Absolute external directories are also supported. The repository root, its
ancestors, legacy `build` root and source-tree directories are forbidden.
Nonempty output directories, including hidden contents, are refused without
cleanup or overwriting. An existing empty directory is allowed. A failed build
retains its workspace; select a fresh output directory for another attempt.
`QEC_IMAGE_DIR` and old image `config.tcl` files are ignored.

Capacity arguments are positive integers: detector and edge ceilings fit 16-bit
metadata, and observable capacity is at most 32. These are input validation
limits, not claims of routability or wider protocol support. Defaults 128/512/32
are provisional until routed feasibility has been measured.

## Flow and outputs

The source allowlist contains only `runtime_surface_decoder.sv`,
`runtime_surface_ps_bridge.sv`, `top_runtime_soc.sv`, its XDC, and the generated
PS wrapper. No packages/common-directory globs or ROM assets are included.
[The block design](bd/top_runtime_soc.md) provides UART1, DDR, GP0 GPIO and one
100 MHz FCLK/reset domain.

Vivado creates `vivado_runtime_soc/`, applies
`Performance_ExplorePostRoutePhysOpt`, runs implementation through bitstream
with four jobs, and requires 100% run progress. After opening the implemented
design it writes:

- `runtime_soc_utilization.rpt`
- `runtime_soc_timing_summary.rpt` with setup/hold and unconstrained-path reporting
- `runtime_soc_drc.rpt`

Both the worst max-delay and min-delay paths must exist and have numeric,
nonnegative slack. Otherwise the script errors before copying the public
`runtime_soc.bit` or exporting `runtime_soc.xsa`. A private implementation
bitstream may already exist when the timing gate fails; that is not an accepted
export. Normal Vivado DRC/bitstream checks remain enabled without severity
changes. Run progress alone is not treated as timing success.

The XSA includes the bitstream and feeds
[the runtime Vitis builder](../vitis/runtime/build_app.md). The build neither
programs a board nor writes flash. The parent integration must run the real
build only after sibling runtime RTL is ready, then review reports and obtain
programming authorization separately.

## Verification boundary

```sh
uv run --with pytest python -m pytest qec/tests/test_runtime_build.py -q
```

The tests run real Tcl control flow with instrumented vendor commands. Their
fake bit/XSA files are explicit test fixtures, not generated FPGA artifacts.
They verify source isolation, argument forwarding, reports, failure gates and
protected outputs. They do not synthesize RTL or establish device feasibility.

# Runtime RTL runner

`run_runtime_rtl.py` invokes installed Vivado **xvlog, xelab and xsim**, without
relying on PATH and without changing existing fixed-image runners. From the
repository root:

```
python scripts/run_runtime_rtl.py --bench core
python scripts/run_runtime_rtl.py --bench bridge
python scripts/run_runtime_rtl.py --bench counter
```

`--vivado-bin` defaults to `/home/toastcheng/amd/2025.2/Vivado/bin`.
`--build-dir` overrides the per-bench default `build/runtime-{bench}`. Use a unique
runtime-prefixed directory for concurrent invocations of the same bench; the
unittest wrapper does this automatically. All simulator libraries, snapshots,
logs and generated vectors stay under that directory, never the old root xsim
library or fixed-image outputs.

The runner compiles only new runtime sources, elaborates the selected top and
runs to `$finish`. Each tool's combined stdout/stderr is saved as
`xvlog.console.log`, `xelab.console.log` or `xsim.console.log`, and printed.
Nonzero exit, `Fatal:`/`FATAL` output, or lack of the selected PASS marker makes
the runner fail, including xsim versions that exit zero after `$fatal`.

For the core bench, the runner parses the actual reference source with Python
AST, compiles only its unchanged dependency-free `decode` function, and executes
it to produce ordered graph/shot/error records in `runtime_vectors.txt`.
Optional Stim/PyMatching imports are not needed; reference algorithm logic is
not copied or replaced. Seed 721093 fixes graph order, masks and sampled shots.
Small graphs enumerate all syndromes; large graphs include boundary patterns
and seeded samples. The generated file records all actual cases for inspection.
The reverse-ordered 128-edge path exercises cycles above 65535.

Test-first evidence: the first core and bridge invocations failed because their
requested modules did not yet exist. Subsequent behavioral RED logs remain in
`build/runtime-red-index/` and `build/runtime-red-conflict/`. Final GREEN logs are
in `build/runtime-core/`, `build/runtime-bridge/` and `build/runtime-counter/`.
The installed tool emits an environment warning about `LIBRARY_PATH`; all three
elaborations and simulations nevertheless completed. No synthetic simulator
output is generated. Physical synthesis, routing and programming are not part
of this runner.

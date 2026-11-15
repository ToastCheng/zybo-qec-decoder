# Runtime RTL test wrapper

`test_runtime_rtl.py` is a standard-library unittest suite, also collectable by
pytest. It runs real core, mailbox and long-counter regressions through
[`run_runtime_rtl.py`](../../scripts/run_runtime_rtl.md), checking both process
exit status and a bench-specific PASS marker.

```
python -m unittest qec.tests.test_runtime_rtl -v
```

`VIVADO_BIN` can override the installed simulator directory. Missing vendor
executables cause an explicit skip, never a software stand-in. Each invocation
allocates a unique `build/runtime-test-{bench}-{suffix}` directory, preserving
logs/vectors and avoiding concurrent library/corpus collisions. The test prints
that directory on success; failures include real captured tool output. There
is a 180-second timeout per complete bench subprocess.

The suite needs neither pytest nor optional Stim/PyMatching packages. Three
real simulator pipelines must finish for three passing tests. These tests do
not run existing fixed-ROM benches, native firmware harnesses or board I/O;
those acceptance boundaries remain separate.

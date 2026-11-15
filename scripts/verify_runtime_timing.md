# Routed runtime timing acceptance

`verify_runtime_timing.py REPORT` reads an actual Vivado timing summary. It
requires Physopt postRoute state, nonempty setup and hold endpoint coverage,
nonnegative WNS/WHS and zero failing endpoints. Missing evidence or a violation
exits nonzero; it never changes constraints or manufactures tool reports.

The original report is the RED regression:

```
python scripts/verify_runtime_timing.py build/runtime-image/runtime_soc_timing_summary.rpt
```

It fails with WNS -3.479 ns, WHS +0.022 ns and 3278 setup failures. Preserve it.
The same checker passes `build/runtime-image-v2/runtime_soc_timing_summary.rpt`
with WNS +0.095 ns and WHS +0.038 ns. This check
is only setup/hold acceptance; inspect DRC, clock frequency, unconstrained paths,
source provenance and capacities separately. It does not prove board operation.

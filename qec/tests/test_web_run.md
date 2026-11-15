# Configurable web-run regression tests

Companion to [`test_web_run.py`](test_web_run.py); exercises [`Lab.run` and its HTTP route](../surface/web.md) without physical hardware.

`settings()` builds a complete fixed d3 Z r3 request with four independently named Stim noise rates and a seed. Parameterized validation tests reject unsupported circuit/graph parameters, noninteger or unsafe seeds, invalid timed faults, and nonfinite, boolean, out-of-range or nonnumeric rates **before** a supplied decoder can be called.

The first end-to-end test was introduced before `Lab.run` existed and failed with `AttributeError`; configuration validation and the HTTP route were subsequently exercised RED before their implementations. The HTTP test initially returned 404 for `/api/run`, then passed once the endpoint was added.

## Coverage

- Identical requests produce identical single-shot responses on this installed Stim/machine/call sequence; seed portability across Stim versions or SIMD architectures is not assumed.
- The returned circuit really contains generated noise operations. Actual per-operation sampled events and Stim-version provenance are present.
- The frozen `sampled_circuit` independently reproduces syndrome, observable and every tick's noise-only Pauli frame, including preparation/reset effects, with a different replay seed.
- Zero noise and no explicit faults yield zero syndrome/observable and no sampled noise events. Zero-noise explicit injections agree with the existing deterministic timed-fault API.
- Maximum 0.75 noise remains supported, distinct seeds change sampled circuits and outcomes, and exported deterministic sampled/corrected circuits reproduce the particular shot rather than resampling it.
- When a correction exists, its independent replay must give zero syndrome and the actual observable XOR selected prediction; unavailable corrections must carry null evidence.
- The loopback HTTP endpoint accepts a pretty-printed 64-fault body exceeding the legacy 4096-byte limit and the maximum safe unsigned seed. Layout exposes supported circuit metadata and run defaults.
- A supplied decoder's prediction remains authoritative, with host-frame, hardware evidence and source labels consistent. Invalid replies and transport exceptions never fall back to software.
- Rebinding Host/Origin pairs receive 403 for the page, layout, run and legacy simulation routes before any decoder call.
- Malformed/missing/extra configuration fields and noise schemas return HTTP 400 without decoder calls; oversized run bodies return 413, and a subsequent valid request reaches the decoder, whose transport failure returns 503.

## Run

From the repository root:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_web_run.py qec/tests/test_web.py
qec/.venv/bin/python -m pytest -q qec/tests
```

The existing `test_web.py` is unchanged and protects legacy `/api/simulate`, local-asset and serial-protocol behavior. Test decoder callbacks represent only the externally supplied logical prediction; they do not claim a real board was contacted.

# General-circuit CLI regression

Companion to [`test_runtime_run.py`](test_runtime_run.py), exercising the [runner](../surface/runtime_run.md) without physical hardware.

The initial tests failed because `runtime_run` did not exist before implementation. The software test executes the real compiler, Stim batch sampler and UF decoder, then independently regenerates every detector and observable from the same source, seed and batch size. It checks the two-observable result, evidence/manifest fields and refusal to overwrite an existing capture directory.

The failure test injects an explicitly named software test device through `decoder_factory`; its decode raises a timeout. It asserts one graph upload, retained wire/error evidence and absence of a successful summary. This does not claim that PL or a serial device was exercised. Invalid scalar settings and a nondeterministic annotated circuit must fail before any serial factory call.

Run from the repository root with the configured Python environment:

```sh
python -m pytest qec/tests/test_runtime_run.py -q
```

Native firmware, real PTY transport, RTL, synthesis/routing and board acceptance have their own tests and evidence. This suite establishes only the runner boundary and archive behavior.

# Annotated circuit examples

Paste these Stim circuits into the web editor, or pass a file to
`python -m qec.surface.run` from the repository root:

- [phase_bell.stim](phase_bell.stim): two physical qubits and two observables.
- [two_repetition_echo.stim](two_repetition_echo.stim): six physical qubits,
  four detectors and two observables.

```sh
python -m qec.surface.run qec/examples/two_repetition_echo.stim --shots 128 --seed 123 --out build/example-run
```

The output directory must be new. Add `--port PORT` only for an already loaded
FPGA with matching firmware. Without a port, this runs the Python decoder.
See the [quick start](../../docs/quickstart.md) for setup and board loading.

These are editable annotated physical circuits, not a whitelist of logical
templates. Encoding, checks and observables must come from the experiment.
The compiler does not turn arbitrary logical gates into a fault-tolerant circuit.
Known memory presets or an explicitly supplied logical description can support
a logical view; a supplied description alone does not certify its physical map.

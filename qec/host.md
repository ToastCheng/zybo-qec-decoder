# Finite-window repetition host validation

Companion to [`host.py`](host.py).

## Contracts and flow

`main()` parses a loopback-or-serial mode, sample count, seed, four-channel noise and endpoint timing settings. Positive shot and timeout checks happen before endpoint creation. Serial mode requires an explicit port; nothing is auto-discovered.

The committed `lut.mem` is loaded relative to this source. Stim produces detector rows and separately sampled logical observables; `pack` maps rows to byte syndromes. The host sends one transaction at a time, wrapping sequence numbers modulo 256. The serial endpoint uses bounded read/write timeouts and resets its input buffer; a finally block closes it. Loopback instead uses the same fixed table in software.

Output is a JSON object, not returned predictions: it reports weighted-reference disagreements, errors against actual sampled observables, identity errors, response-cycle extrema and median host roundtrip nanoseconds. Changing `--noise` changes the sampled circuit and weighted reference, not the committed table. These two disagreement metrics need not coincide.

Even serial mode is labelled `serial-unverified-hardware` with `fpga_measured=false`: opening a port alone does not attest device identity. Host roundtrip includes serialization and scheduling; reply cycles refer to a different acceptance-to-result boundary. Loopback cycle fields are placeholders.

## Callable index

- `main` — Sample Stim windows, exchange each packed syndrome, and print aggregate validation JSON.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python qec/host.py --mode loopback --shots 32 --seed 90210
python -m pytest -q qec/tests/test_transport.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.

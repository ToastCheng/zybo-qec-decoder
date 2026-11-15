# Runtime annotated-circuit web server

`runtime_web.py` serves the general physical Clifford-circuit editor and a single-shot experiment API. It does not synthesize logical programs into fault-tolerant circuits. The fixed-image web implementation is separate and unchanged.

## Launch and request boundary

From the repository root with the QEC environment active:

```sh
python -m qec.surface.runtime_web --port 18767
# Only for an independently accepted matching runtime FPGA image:
python -m qec.surface.runtime_web --port 18767 --serial-port /dev/ttyUSB0
```

The first command is explicitly Software-only and never opens serial. The second uses `RuntimeSerialDecoder` on explicit Run; it never substitutes Software after a hardware error. Do not run the second command against a legacy fixed graph image. Runtime image physical acceptance is a separate parent integration task.

`make_server` binds IPv4 loopback. Exact loopback Host authority and optional Origin allowlists are checked before serving assets or invoking the lab, including requests with no Origin. Responses disable caching and apply same-origin CSP. Only `/`, `/app.js`, `/style.css`, and `/api/config` are GET routes. Config reads the phase-Bell source example and reports Software/FPGA without querying a board. POST routes are `/api/validate` and `/api/run`; the UI uses only Run. POST work is serialized with a nonblocking lock (429 when busy), bounded Content-Length (600000 bytes), and socket timeout. Errors return 400 with an `error` string and no stale result. The server is intended for trusted local use, not public hosting.

## Compilation and noise

`_prepare` requires exactly circuit, reference, seed and added_noise fields. Seed is an integer in 0..2^53-1; added depolarization is finite in 0..0.75. It calls the bounded generic Stim parser before inserting noise, so record feedback, sweep controls and resource excess fail before unitary targets are repurposed as noise targets. There is no template or Clifford gate-name whitelist.

At zero added noise, the submitted circuit and reference are preserved. At positive added noise, existing stochastic instructions remain, each one/two-qubit unitary target group gets DEPOLARIZE1/2, and other unitary Pauli-product operations get single-qubit depolarization on their support. Measurement/reset instructions do not receive this *gate* noise. The augmented circuit becomes its own graph reference; a supplied unrelated noisy reference is not used. Stim may canonically merge adjacent equal instructions. Exact deterministic-detector checks, reference compatibility, graphlike signature rejection, edge/observable capacities and hashes are owned by [runtime_circuit](runtime_circuit.md).

`_compile_bounded` executes this preparation and compilation in a separate Python worker with a 15-second `subprocess.run` deadline. Timeout kills/waits for that child and surfaces an explicit error. The worker does not instantiate serial transport. Python/source resource budgets bound parsing and flattening independently of this deadline.

## Single-shot and hardware flow

`RuntimeLab.run` first compiles before any port is opened. One Stim FlipSimulator instance (batch size 1, stabilizer randomization disabled) produces Pauli frames, cumulative detector events and cumulative observable flips at each TICK segment. The final little-endian masks and trace therefore refer to the same actual sampled shot. Seed reproducibility is scoped to Stim version, machine/SIMD, batch size and call sequence, not a portable universal random stream. No physical correction or counterfactual corrected trajectory is claimed.

Software mode invokes the unweighted graph decoder and reports cycles=null, transactions=[], source=Software. FPGA mode opens exclusive runtime transport, reads actual capacities, recompiles against those limits, uploads the exact ordered graph on every run, and decodes the sampled syndrome. It returns source=FPGA, reported cycles, loaded identity words and exact hex transaction evidence. Transport errors propagate; there is no fallback. Invalid input is rejected before opening serial; a valid circuit exceeding the connected image's smaller advertised capacity can only be rejected after reading that identity.

Each trace frame adds `diagram`, an array of structured instructions derived directly from actual flattened Stim operations: name, single/pair/product kind, exact text, and typed targets (qubit, Pauli basis, combiner, inversion, or measurement record). This is additive to the existing operation strings and does not change API/CLI decoding semantics. The browser requires this metadata and asks for a runtime-server restart if an older process lacks it. No wire positions or correction paths are inferred.

The response includes compiled circuit/DEM/graph provenance, counts, operations, detector annotation timing, trace, seed, syndrome, truth, prediction and source. Masks remain unsigned 32-bit-valued JSON numbers. Returned prediction is an observable mask, not a physical correction path. The graph uses unweighted independent edges even where DEM retains separator correlations.

## Verification

```sh
python -m pytest qec/tests/test_runtime_web.py -q
RUNTIME_WEB_URL=http://127.0.0.1:18767 python -m pytest qec/tests/test_runtime_web.py -q
```

The first command includes real Stim and Software decoding plus explicitly labeled fake-transport orchestration tests. The second adds real Chromium UI verification against a separately started simulation server. See [browser test](../tests/test_runtime_web_ui.md). Neither establishes physical FPGA operation.

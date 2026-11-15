# Runtime web Python regression suite

`test_runtime_web.py` is discovered by the existing `make test` pytest entry point. Run it directly with `python -m pytest qec/tests/test_runtime_web.py -q` from the repository root and the QEC environment active.

Tests execute the real bounded compiler worker, Stim circuits and Software graph decoder. They cover zero-noise explicit-reference requirements, preservation of base noise when adding depolarization, numeric validation, deterministic seed replay, variable physical qubit counts, same-shot detector/observable trace masks, and an unlisted three-qubit Clifford circuit. Both checked-in runtime examples (phase_bell and two_repetition_echo) run with their actual defaults and retain two observable bits. A separate bit31 example exercises the uint32 output boundary. The sparse q0/q1023 metadata test checks actual Stim two-qubit typing, Pauli-product combiners/bases, record targets, and the 1024 indexed-qubit safety boundary.

The gate-noise preparation regression uses S, SQRT_X, CX and Pauli-product SPP instead of a template whitelist, preserves an existing X_ERROR, and compares noiseless operations after insertion. Feedback targets must fail before noise is inserted. The compiler deadline regression injects subprocess.TimeoutExpired to check its surfaced error, not to claim a hardware timeout experiment.

The fake serial class is explicitly named FAKE-NOT-A-BOARD and tests orchestration only: no serial for validation or invalid input, capacity identity before upload, upload on every Run, graph dimensions, returned source/cycles/hex evidence, context closure and propagation of simulated wire failures. Its FPGA response label is an assertion about the production routing branch, not physical FPGA evidence.

The HTTP test starts a disposable ephemeral Software server and exercises config, assets, validate/run, next-request behavior after invalid input, hostile Host/Origin rejection, oversize bodies and path traversal denial. It shuts down its server in finally.

`test_opt_in_chromium_runtime_ui` skips unless RUNTIME_WEB_URL names a separately started isolated Software preview. With it set, this suite invokes [the real Chromium regression](test_runtime_web_ui.md), including through `make test`. No hardware or normal user preview should be used as that target.

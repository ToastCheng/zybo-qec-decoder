# Stim replay, bounded HTTP and no silent hardware fallback

Companion to [`test_web.py`](test_web.py).

## Test flow and assertions

lab() creates a software Lab. Tests replay singleton and exhaustive X/Z legacy masks plus random mixed faults in Stim, check graph and physical representatives separately, and demonstrate a zero-syndrome logical chain still fails. Timed-fault tests check detector availability, frame propagation, all tick placements, independent corrected-circuit samples, multitime signature composition and bounded caches. Stub callbacks prove external prediction drives host_frame and invalid/failed hardware never becomes simulated output. Real local HTTP servers exercise assets, path allowlisting, body bounds, cross-origin rejection and 400/503 recovery. SerialDecoder uses a PTY with split/corrupt replies, checksum recovery, exclusive-port contention and bounded lock waits.

## Test functions and helpers

- `test_injection_replays_real_stim_and_decoder_correction`
- `test_input_bounds_and_logical_failure_are_explicit`
- `test_http_api_rejects_bad_requests_and_recovers`
- `test_multiqubit_faults_and_exported_replays_match_stim`
- `test_http_assets_are_local_and_cross_origin_writes_rejected`
- `lab`
- `test_tick_faults_replay_real_circuit_without_future_detectors`
- `test_fpga_prediction_drives_host_frame_and_failure_never_falls_back`
- `test_tick_correction_is_independently_replayed_and_frames_propagate`
- `test_serial_transport_real_pty_framing_failure_and_recovery`
- `test_http_tick_faults_and_hardware_failure_recovery`
- `test_cli_accepts_explicit_serial_source`
- `test_serial_port_contention_is_explicit_and_lock_timeout_is_bounded`
- `test_multitime_replay_and_zero_syndrome_logical_chain`
- `test_configured_hardware_cannot_silently_become_simulated`
- `test_layout_is_derived_from_stim`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Temporary loopback HTTP servers and Unix PTYs are closed in finally blocks. CLI help currently invokes qec/.venv/bin/python explicitly. These tests verify backend/transport contracts, not browser rendering or board latency.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_web.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.

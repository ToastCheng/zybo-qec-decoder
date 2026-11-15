# Exhaustive repetition core timing bench

Source: [`tb_qec_decoder.sv`](tb_qec_decoder.sv).

## Stimulus and oracle

The bench loads `qec/lut.mem` as its expected prediction array and uses an 8 ns
clock. After synchronous reset, it submits all 256 syndrome bytes. This verifies
ROM address/data fidelity, not independent statistical optimality of the table.

## Checks and scheduling

Inputs change on falling edges. For each accepted shot, the bench rejects valid
before the two-edge result, then requires `prediction === expected[i]` and
`cycles === 2`. It next holds out_ready low for seven cycles while attempting to
overwrite the shot, requiring no input readiness and an unchanged output. Reset
must immediately gate both handshakes and clear a held result on the next edge.
A final reset aborts an accepted in-flight shot and checks no stale result leaks.
A separate 100000 ns watchdog catches deadlock; success prints an explicit PASS.

## Verification and related files

Run `python scripts/qec_sim.py` from root. The same bench runs against synthesized
ROM via `python scripts/qec_sim.py --netlist` after the core synthesis artifact
exists. The runner treats HDL fatals or missing PASS as failure. See
[`../common/qec_decoder.sv`](../common/qec_decoder.sv) and `scripts/qec_sim.py`.
No physical UART or board is needed.

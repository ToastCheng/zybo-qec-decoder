# Runtime-configurable QEC decoder implementation contract

Status: implementation in progress; not a claim of board acceptance.

## Verified integration so far

- Parent baseline after core/compiler/host integration: 242 tests passed, 31 skipped.
- Real Vivado core, mailbox and counter benches passed; each recompiled in isolated parent-run directories under `build/runtime-test-*`.
- Additional actual compiler-to-core run: `build/runtime-compiled-circuits/summary.json` and `xsim.log`. Loaded phase-Bell (2 qubits, 2 observables), two repetition echoes (6 qubits, 2 observables), d3 Z/r3, d3 X/r5 and d5 Z/r3 into the same simulator image, with 128 actual Stim shots per circuit. Core predictions/errors matched the Python UF reference; the d3 X/r5 sample had two logical failures against Stim truth, retained rather than hidden. A separately identified synthetic long-path diagnostic exercises the 16-bit cycle carry.
- The pipelined image in `build/runtime-image-v2/` passed routed timing at unchanged capacity and 100 MHz (WNS +0.095 ns, WHS +0.038 ns). Matching ARM firmware built successfully against that XSA; source and bitstream/ELF pairing is recorded in `complete-bundle-verification.json`. No runtime bitstream has been programmed onto the board.


## Goal

One FPGA image accepts circuit-specific graph configuration and detector samples at runtime. Inputs are detector-annotated Clifford Stim circuits with declared observables, not a whitelist of memory/H/CX templates. Raw Clifford gates alone do not define a QEC experiment. Reject nondeterministic detectors, unsupported non-graphlike noise, detectorless logical faults and lossful endpoint/mask projections explicitly. Support variable qubit/detector counts within measured device capacities and preserve all observable bits. No software substitute for FPGA results.

## Initial hardware capacities (subject to routed feasibility)

MAX_DETECTORS=128, MAX_EDGES=512, MAX_OBSERVABLES=32, independently parameterized for testing and future images. These are decoder capacities, not a fixed physical-qubit count. Return actual capacities through identity. Edge endpoints are unsigned 16-bit indices; runtime boundary index equals detector_count. Observable mask is unsigned 32-bit. One unweighted half-edge UF/forest-peeling shot at a time; retain deterministic input edge order. Do not claim weighted MWPM equivalence or adaptive quantum feedforward.

## Core configuration

New `runtime_surface_decoder` module; preserve existing fixed-image sources. `cfg_begin` supplies detector_count, edge_count, observable_count and invalidates prior configuration. `cfg_write` supplies sequential edge_index, endpoint_a, endpoint_b, observable_mask. Reject duplicates/out-of-order writes, invalid endpoints, self-loops, masks outside observable_count, oversize dimensions and changes while busy. `cfg_commit` succeeds only after every declared edge is validated and written. Failed or incomplete load cannot decode. Configuration remains across shot reset/abort, clears on full reset. No writes while a result is held. Decode input is MAX_DETECTORS bits, upper unused bits must be zero; prediction is MAX_OBSERVABLES bits. Output includes decode_error and acceptance-to-result cycles. Configuration errors need an acknowledged error signal rather than silent acceptance.

## PS/PL command mailbox

New `runtime_surface_ps_bridge`, same-FCLK GPIO ctrl/status handshake, separate from fixed bridge. ctrl[31] toggle, ctrl[27:24] opcode, ctrl[23:16] index, ctrl[15:0] data. status[31] ack toggle, status[30] result-complete, status[29] error, status[15:0] read data. Each command acknowledged after its effect. Commands:

- 1 write staging word: indices 0 detector_count, 1 edge_count, 2 observable_count; 3 edge_index, 4 endpoint_a, 5 endpoint_b, 6 mask low16, 7 mask high16.
- 2 begin configuration using staged dimensions; reject invalid/busy.
- 3 append staged edge using core sequential validation.
- 4 commit graph; update successful graph generation counter only after acceptance.
- 5 write syndrome word at index (little endian 16-bit words).
- 6 decode; acknowledge only after completion; preserve prediction/error/cycles for reads.
- 7 read metadata: 0 protocol version=2, 1 max detectors, 2 max edges, 3 max observables, 4 configured detectors, 5 configured edges, 6 configured observables, 7 config-valid, 8 generation low16, 9 generation high16; 10 prediction low16, 11 prediction high16, 12 cycles low16, 13 cycles high16, 14 decode-error.
- 8 abort shot/clear staging syndrome (not graph); acknowledge completion. Full reset clears graph.

The mailbox index width is sufficient for initial capacity. Range-check all indices and high syndrome bits; do not alias invalid indices. Software writes all active syndrome words before decode. New graph begin clears syndrome. No runtime identity digest is claimed cryptographically verified: dimensions/generation are PL-sourced; host archives exact uploaded ordered edges and validates transport checksums.

## Serial runtime protocol

New separate runtime firmware and host; do not reuse or break old C3/3C frames. Request frame: D4, seq:u8, opcode:u8, length:u16le, payload:length, crc32:u32le. CRC is standard zlib/IEEE CRC32 over header and payload, excluding CRC field. Response: 4D, same seq, status:u8 (0 success, 1 invalid, 2 not configured, 3 decoder error, 4 timeout), length:u16le, payload, crc32:u32le. Max payload 512 bytes. Reject overflow/malformed CRC, partial timeout and unknown commands, then accept next valid frame. No boot flash writes.

Opcodes: 1 identity (empty payload; response 15 uint32le values indexed as mailbox metadata 0..14); 2 begin (three uint16le dimensions); 3 append edges (one or more 10-byte records: index:u16,a:u16,b:u16,mask:u32); 4 commit (empty); 5 decode (ceil(detectors/8) syndrome bytes; response prediction:u32le,cycles:u32le,decode_error:u8); 6 abort (empty). Upload sends begin, ordered chunks, commit, then identity and compares dimensions/config-valid/generation. Changing graph invalidates old decoder evidence. Failed upload never leads to decode against stale graph. Uncertain serial completion blocks all subsequent requests until explicit bounded `resynchronize()` consumes and validates the outstanding reply; it then requires graph reload. If the reply cannot be recovered, the session remains unusable rather than blindly issuing abort/reload. Opcode 8 does not preempt an unacknowledged mailbox decode.

## Verification order

1. Existing tests baseline: 162 passed,31 skipped before edits.
2. Compiler and frame/parser tests, native firmware harness, actual RTL loading multiple graph sizes and multibit masks without rebuilding.
3. Full mailbox/transport integration and invalid-load/next-valid recovery, backpressure, reset and independent cycles.
4. Synthesis and route/resource/timing checks on Zybo Z7-10; adjust published capacities based on evidence.
5. Matching volatile bitstream/firmware board acceptance only with authorization; no flash writes.
6. General circuit editor, explicit simulation+FPGA run and network-free replay; real screenshot and README after actual acceptance.

Preserve all preexisting dirty graph-specific-H work and historical archives. New modules and source-specific adjacent Markdown are required. Every milestone must state which verification boundary has actually passed.

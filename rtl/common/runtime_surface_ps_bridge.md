# Runtime PS mailbox

`runtime_surface_ps_bridge.sv` instantiates
[`runtime_surface_decoder`](runtime_surface_decoder.md) and provides the version-2
mailbox in [the shared plan](../../docs/runtime-decoder-plan.md). It never reads
the old fixed ROM or delegates decoding to PS software.

## Ports, clock and parameters

Ports are `clk` (input bit), `rst` (input bit, synchronous active-high full reset),
`ctrl` (input 32 bits), `status` (output 32 bits). PS GPIO and this bridge must
share the same FCLK; this is not a CDC synchronizer. Parameters are
`MAX_DETECTORS=128`, `MAX_EDGES=512`, `MAX_OBSERVABLES=32`, forwarded to the core.
The mailbox's 8-bit syndrome-word index can represent up to 4096 detector bits;
other count fields are unsigned 16-bit and observables are at most 32. The
initial capacities fit this addressing contract.

`ctrl[31]` is the request toggle; [30:28] are reserved, [27:24] opcode,
[23:16] index, [15:0] data. `status[31]` is acknowledged toggle, [30] indicates a
saved completed decode, [29] is the last command's error, [28:16] are zero and
[15:0] is read data (zero for non-read commands).

Start from full-reset ctrl/status zero. For each command, invert ctrl[31], set
opcode/index/data and hold **the entire ctrl word** until status[31] matches.
There is one outstanding command: do not toggle again or change fields early.
Status remains stable until another command acknowledges. A nonzero index for a
command without an index is rejected, not silently aliased to index zero.
Reserved data bits for such commands are ignored; send zero.

## Commands

| Opcode | Index | Action |
|---|---|---|
| 1 | 0–7 | Store a 16-bit staging register |
| 2 | 0 only | Begin with staged dimensions; clear staged syndrome and previous result |
| 3 | 0 only | Append staged edge; acknowledge core validation result |
| 4 | 0 only | Commit; increment 32-bit generation only on core acceptance |
| 5 | Active syndrome word index | Write little-endian 16 detector bits |
| 6 | 0 only | Decode; acknowledge only when the result has been saved |
| 7 | 0–14 | Read one metadata word |
| 8 | 0 only | Abort/clear shot and saved result; preserve graph and generation |

Staging registers: 0 detector count, 1 edge count, 2 observable count, 3 edge
index, 4 endpoint A, 5 endpoint B, 6 mask low16, 7 mask high16. Full reset zeros
all eight. Begin clears syndrome words/written flags, not these staging registers.
Software must stage every field it intends to change. No command writes the
active graph except the core-validated configuration path.

Opcode 5 rejects unconfigured use, any inactive/out-of-capacity word, and nonzero
unused bits in the final partial word. A rejected write does not alias another
word or satisfy its written flag. **All active words must be explicitly written
for each decode**, including words whose data are zero. Successful decode launch
consumes these written flags. Decode before configuration or with any missing
word acknowledges error without starting a shot.

Metadata words:

| Index | Value |
|---|---|
| 0 | Protocol version 2 |
| 1, 2, 3 | MAX_DETECTORS, MAX_EDGES, MAX_OBSERVABLES |
| 4, 5, 6 | Last begun detector, edge, observable counts |
| 7 | Configured bit (zero-extended) |
| 8, 9 | Successful graph generation low16, high16 |
| 10, 11 | Saved prediction low16, high16 |
| 12, 13 | Saved cycles low16, high16 |
| 14 | Saved decode-error bit |

Words 4–6 can describe a rejected/incomplete begin and must not be used without
word 7. Generations wrap modulo 2^32 and are not cryptographic identities.
Prediction bits above a smaller MAX_OBSERVABLES are zero-extended for metadata.
Reads preserve saved results. `status[29]` is per-command: a metadata read can
succeed after a failed decode; read word 14 for that decode's saved error.
`status[30]` persists across reads/staging writes and clears on begin, next decode
launch or abort. Algorithm errors still set completion and acknowledge decode
with status[29]=1. Failed pre-launch commands retain the previous saved result.

## Sequencing and reset

Configuration ISSUE states drive one core strobe, WAIT_CONFIG waits for its
registered ack, then the mailbox acknowledges success/error. This explicitly
acknowledges invalid configurations, rather than waiting forever on `in_ready`.
LAUNCH holds core in_valid to acceptance; WAIT_RESULT saves all result fields and
retires the core. Abort uses a separate core `shot_abort`, **not** its full reset,
then acknowledges after clearing syndrome, flags and saved result. Full `rst`
clears validity, dimensions, generation, staging, syndrome, result and ack toggle.

The one-outstanding-toggle contract means opcode 8 cannot preempt an outstanding
opcode 6: it is sent after its ack, like other commands. Core-level `shot_abort`
can interrupt an active shot directly. If a future requirement demands PS
preemption of a wedged outstanding command, it needs a separate abort/reset
control or an explicitly amended resynchronization protocol; blindly toggling
again can equal the old ack before any abort occurs. This implementation does
not claim that unsafe operation works.

## Reproduction

- `python scripts/run_runtime_rtl.py --bench bridge` runs reduced capacities
  20/16/32, invalid-load recovery, two-word syndrome changes and real decodes.
- `python scripts/run_runtime_rtl.py --bench counter` runs default capacities and
  a 132100-cycle decode, reading both cycle halves without forcing internal
  counters.

These are real xvlog/xelab/xsim behavioral simulations. Synthesis/routing and
physical GPIO/firmware integration remain separate acceptance boundaries.

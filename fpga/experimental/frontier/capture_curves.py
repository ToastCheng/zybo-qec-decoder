"""Run the 24-point X/Z d3/d5 benchmark corpus on a connected Zybo Z7-10 over UART."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path('/home/toastcheng/dev/zybo-qec-decoder')
sys.path.insert(0, str(ROOT))
from qec.surface.host import DecoderIdentity, DecoderReply, GraphDecoder, ProtocolError


class FrontierDecoder(GraphDecoder):
    """UART host client for the 0xd505 programmable parity-frontier bitstream."""

    def __init__(self, port, **kwargs):
        """Open the UART client with no cached program CRC."""
        super().__init__(port, **kwargs)
        self._program_crc = None

    def frontier_identity(self):
        """Query the 17-word metadata and return (DecoderIdentity, program_crc).

        Verifies protocol version 0xd505 and 128/1024/1 capacities before
        adapting the first 15 words to DecoderIdentity.
        """
        payload = self._transact(1)
        if len(payload) != 68:
            self._loaded = None
            raise ProtocolError('frontier identity width', **self._raw_last())
        words = struct.unpack('<17I', payload)
        if words[:4] != (0xD505, 128, 1024, 1) or any(w > 65535 for w in words):
            self._loaded = None
            raise ProtocolError('not the d3/d5 exact frontier image', **self._raw_last())
        return DecoderIdentity((2,) + words[1:15]), (words[15] | words[16] << 16)

    def identity(self):
        """Return DecoderIdentity without the trailing program CRC."""
        return self.frontier_identity()[0]

    def load_program(self, detectors, records, expected_crc):
        """Upload 10-byte DP program records in 51-record chunks and commit.

        Checks that the board reports a valid program with the requested
        dimensions, incremented generation, and matching hardware CRC-32.
        """
        with self._lock:
            self._loaded = None
            self._program_crc = None
            before, _ = self.frontier_identity()
            self._ack(2, struct.pack('<HHH', detectors, len(records), 1))
            for start in range(0, len(records), 51):
                chunk = b''.join(
                    struct.pack('<HHHI', index, *records[index])
                    for index in range(start, min(start + 51, len(records)))
                )
                self._ack(3, chunk)
            self._ack(4)
            after, crc = self.frontier_identity()
            if (not after.valid or (after.detectors, after.edges, after.observables) != (detectors, len(records), 1)
                    or after.generation != (before.generation + 1) & 0xFFFFFFFF or crc != expected_crc):
                raise ProtocolError(f'frontier program CRC/identity mismatch {crc:08x} != {expected_crc:08x}',
                                    **self._raw_last())
            self._loaded = after
            self._program_crc = crc
            self.uploaded_edges = tuple(tuple(r) for r in records)
            return after

    def decode_checked(self, syndrome):
        """Decode one packed syndrome without per-shot identity polling.

        Validates reply width, positive cycle count, error flag, and 1-bit
        prediction. Call verify_intact() after the point to recheck metadata/CRC.
        """
        with self._lock:
            loaded = self._loaded
            if loaded is None:
                raise RuntimeError('program load required before decode')
            payload = self._transact(5, syndrome.to_bytes((loaded.detectors + 7) // 8, 'little'))
            if len(payload) != 9:
                self._loaded = None
                raise ProtocolError('decode reply width', **self._raw_last())
            prediction, cycles, error = struct.unpack('<IIB', payload)
            if not cycles or error or prediction > 1:
                self._loaded = None
                raise ProtocolError('invalid frontier decode reply', **self._raw_last())
            return DecoderReply(prediction, cycles, False)

    def verify_intact(self):
        """Confirm the loaded program identity and hardware CRC did not change."""
        after, crc = self.frontier_identity()
        if (self._loaded is None or not after.valid or after.words[:10] != self._loaded.words[:10]
                or crc != self._program_crc):
            self._loaded = None
            raise ProtocolError('frontier program changed during capture', **self._raw_last())


class FastUFDecoder(GraphDecoder):
    """UF host client that verifies graph identity once per point instead of per shot."""

    def decode_checked(self, syndrome):
        """Decode one packed syndrome and check reply width, cycles, and error flag."""
        with self._lock:
            loaded = self._loaded
            if loaded is None:
                raise RuntimeError('graph load required before decode')
            payload = self._transact(5, syndrome.to_bytes((loaded.detectors + 7) // 8, 'little'))
            if len(payload) != 9:
                self._loaded = None
                raise ProtocolError('decode reply width', **self._raw_last())
            prediction, cycles, error = struct.unpack('<IIB', payload)
            if not cycles or error or prediction >> loaded.observables:
                self._loaded = None
                raise ProtocolError('invalid UF decode reply', **self._raw_last())
            return DecoderReply(prediction, cycles, False)

    def verify_intact(self):
        """Confirm the board still reports the same loaded UF graph."""
        after = self.identity()
        if self._loaded is None or not after.valid or after.words[:10] != self._loaded.words[:10]:
            self._loaded = None
            raise ProtocolError('UF graph changed during capture', **self._raw_last())


def expected_frontier_cycles(width, operations, syndrome):
    """Exact PL cycle count for the frontier FSM (1 cycle for zero syndrome).

    For nonzero syndromes: `groups` cycles in INIT, `2 + 6 * groups` per DP op
    (PROGRAM_READ, PROGRAM_PREP, then 6-cycle group sweeps), plus 2 cycles for
    FINAL_READ and FINAL_LATCH.
    """
    if syndrome == 0:
        return 1
    groups = 1 << (max(width, 2) - 2)
    return groups + operations * (2 + 6 * groups) + 2


def main():
    """Replay every corpus point on the board and save results and UART wire logs.

    For matching, first verifies that a zero-mask record is rejected in PL.
    Checks every hardware prediction (and frontier cycle count) against the
    corpus reference before writing per-point JSON files and summary.json.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--decoder', choices=('uf', 'matching'), required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', default='/dev/ttyUSB1')
    args = parser.parse_args()
    manifest = json.loads((args.corpus / 'manifest.json').read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    cls = FrontierDecoder if args.decoder == 'matching' else FastUFDecoder
    with cls(args.port, timeout=3.0) as board:
        if args.decoder == 'matching':
            # Confirm PL rejects an invalid zero-mask record and leaves decode disarmed.
            board._ack(2, struct.pack('<HHH', 3, 2, 1))
            try:
                board._ack(3, struct.pack('<HHHI', 0, 0, 0, 1))
            except ProtocolError as exc:
                assert exc.status is not None
            else:
                raise AssertionError('frontier accepted zero-mask record')
            ident, _ = board.frontier_identity()
            assert not ident.valid
        point_summaries = []
        for entry in manifest['points']:
            name = entry['name']
            point = json.loads((args.corpus / f'{name}.json').read_text())
            board.transactions = []
            if args.decoder == 'matching':
                loaded = board.load_program(point['detectors'], point['records'], point['program_crc'])
            else:
                loaded = board.load_graph(point['detectors'], point['uf_edges'], 1)
            rows = []
            for s in point['unique_syndromes']:
                reply = board.decode_checked(s)
                expected = point['references'][str(s)][args.decoder]
                assert reply.prediction == expected and not reply.decode_error, (name, s, reply, expected)
                if args.decoder == 'matching':
                    want_cycles = expected_frontier_cycles(point['width'], point['operations'], s)
                    assert reply.cycles == want_cycles, (name, s, reply.cycles, want_cycles)
                rows.append(dict(syndrome=f'{s:018x}', prediction=reply.prediction, cycles=reply.cycles))
            board.verify_intact()
            (args.output / f'{name}-results.json').write_text(json.dumps(dict(
                decoder=args.decoder, name=name, loaded=list(loaded.words),
                program_crc=point['program_crc'] if args.decoder == 'matching' else None,
                syndromes=rows), indent=2) + '\n')
            board.save_archive(args.output / f'{name}-wire.json')
            point_summaries.append(dict(name=name, unique=len(rows),
                                        cycles_min=min(r['cycles'] for r in rows),
                                        cycles_max=max(r['cycles'] for r in rows)))
            print(f'{args.decoder} {name}: {len(rows)} syndromes OK (max {point_summaries[-1]["cycles_max"]} cycles)', flush=True)
    (args.output / 'summary.json').write_text(json.dumps(point_summaries, indent=2) + '\n')


if __name__ == '__main__':
    main()

"""Verify archived UF and fixed-matching UART logs against reference vectors and RTL cycles."""
import csv
import json
from pathlib import Path
import statistics
import struct
import sys
import zlib


def frame(hex_string, magic):
    """Decode a hex UART frame, verifying its magic byte, length, and CRC-32.

    Returns (seq, opcode_or_status, payload).
    """
    data = bytes.fromhex(hex_string)
    assert data[0] == magic and len(data) >= 9
    length = int.from_bytes(data[3:5], "little")
    assert len(data) == length + 9
    assert zlib.crc32(data[:-4]) == int.from_bytes(data[-4:], "little")
    return data[1], data[2], data[5:-4]


def verify(root):
    """Validate UF (v2) and fixed-matching (0xd303) wire logs against vectors and RTL.

    Checks every frame CRC and sequence number, confirms matching saw one
    rejected tampered-graph write, matches every shot's syndrome, prediction,
    and cycle count to vectors.txt and rtl-latency.csv, and returns per-population
    timing and logical-failure summaries.
    """
    vectors = [line.split() for line in (root / "vectors.txt").read_text().splitlines()[1:]]
    rtl = list(csv.DictReader((root / "rtl-latency.csv").open()))
    count = int((root / "vectors.txt").read_text().splitlines()[0])
    assert len(vectors) == len(rtl) == count
    summaries = {}
    for name, version in (("uf", 2), ("matching", 0xD303)):
        wire = json.loads((root / name / "wire.json").read_text())
        results = json.loads((root / name / "results.json").read_text())
        real_count = results.get("real_shots", 512)
        assert 0 < real_count <= count - 513
        shots = []
        rejected = 0
        for i, record in enumerate(wire["transactions"]):
            seq, op, tx = frame(record["tx_hex"], 0xD4)
            rseq, status, rx = frame(record["rx_hex"], 0x4D)
            assert seq == rseq == i % 256
            if status:
                assert name == "matching" and op == 3
                rejected += 1
                continue
            if op == 1:
                words = struct.unpack("<15I", rx)
                assert words[0] == version
            elif op == 5:
                prediction, cycles, error = struct.unpack("<IIB", rx)
                assert not error and cycles > 0
                shots.append((int.from_bytes(tx, "little"), prediction, cycles))
        assert len(shots) == len(results["shots"]) == count
        assert rejected == (1 if name == "matching" else 0)
        for i, (s, pred, cycles) in enumerate(shots):
            v = vectors[i]
            assert s == int(v[0], 16)
            assert pred == int(v[2 if name == "matching" else 3])
            assert cycles == int(rtl[i][name + "_cycles"])
            row = results["shots"][i]
            assert (s, pred, cycles) == (row["syndrome"], row["prediction"], row["cycles"])
        stats = {}
        for pop, indices in (("real", range(real_count)), ("uniform", range(real_count, real_count + 512)),
                             ("diagnostic", range(real_count + 512, count))):
            cycles = [shots[i][2] for i in indices]
            stats[pop] = dict(count=len(cycles), mean_cycles=statistics.mean(cycles),
                              median_cycles=statistics.median(cycles), min_cycles=min(cycles),
                              max_cycles=max(cycles), mean_us=statistics.mean(cycles) / 100,
                              failures=sum(shots[i][1] != int(vectors[i][5]) for i in indices)
                              if pop == "real" else None)
        summaries[name] = dict(transactions=len(wire["transactions"]), verified_shots=len(shots),
                               rejected_wrong_graph=rejected, populations=stats)
    summaries["real_empty_syndromes"] = sum(int(v[0], 16) == 0 for v in vectors[:real_count])
    summaries["real_mean_latency_ratio_matching_over_uf"] = (
        summaries["matching"]["populations"]["real"]["mean_cycles"] /
        summaries["uf"]["populations"]["real"]["mean_cycles"])
    return summaries


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))

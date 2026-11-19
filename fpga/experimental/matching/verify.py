"""Independently verify archived wire records, references and paired statistics."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import struct
import sys
import zlib


def frame(hex_string, magic):
    data = bytes.fromhex(hex_string)
    assert data[0] == magic and len(data) >= 9
    length = int.from_bytes(data[3:5], "little")
    assert len(data) == length + 9
    assert zlib.crc32(data[:-4]) == int.from_bytes(data[-4:], "little")
    return data[1], data[2], data[5:-4]


def verify(root):
    vectors = [line.split() for line in (root / "vectors.txt").read_text().splitlines()[1:]]
    rtl = list(csv.DictReader((root / "rtl-latency.csv").open()))
    assert len(vectors) == len(rtl) == 1050
    summaries = {}
    for name, version in (("uf", 2), ("matching", 0xD303)):
        wire = json.loads((root / name / "wire.json").read_text())
        results = json.loads((root / name / "results.json").read_text())
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
        assert len(shots) == len(results["shots"]) == 1050
        assert rejected == (1 if name == "matching" else 0)
        for i, (s, pred, cycles) in enumerate(shots):
            v = vectors[i]
            assert s == int(v[0], 16)
            assert pred == int(v[2 if name == "matching" else 3])
            assert cycles == int(rtl[i][name + "_cycles"])
            row = results["shots"][i]
            assert (s, pred, cycles) == (row["syndrome"], row["prediction"], row["cycles"])
        stats = {}
        for pop, indices in (("real", range(512)), ("uniform", range(512, 1024)),
                             ("diagnostic", range(1024, 1050))):
            cycles = [shots[i][2] for i in indices]
            stats[pop] = dict(count=len(cycles), mean_cycles=statistics.mean(cycles),
                              median_cycles=statistics.median(cycles), min_cycles=min(cycles),
                              max_cycles=max(cycles), mean_us=statistics.mean(cycles) / 100,
                              failures=sum(shots[i][1] != int(vectors[i][5]) for i in indices)
                              if pop == "real" else None)
        summaries[name] = dict(transactions=len(wire["transactions"]), verified_shots=len(shots),
                               rejected_wrong_graph=rejected, populations=stats)
    summaries["real_empty_syndromes"] = sum(int(v[0], 16) == 0 for v in vectors[:512])
    summaries["real_mean_latency_ratio_matching_over_uf"] = (
        summaries["matching"]["populations"]["real"]["mean_cycles"] /
        summaries["uf"]["populations"]["real"]["mean_cycles"])
    return summaries


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))

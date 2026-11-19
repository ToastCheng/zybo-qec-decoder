"""Independently verify all 48 board point wire logs, map to truth, and plot."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import struct
import zlib

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import beta


def parse_frame(hex_string, magic):
    data = bytes.fromhex(hex_string)
    assert data[0] == magic and len(data) >= 9
    length = int.from_bytes(data[3:5], 'little')
    assert len(data) == length + 9
    assert zlib.crc32(data[:-4]) == int.from_bytes(data[-4:], 'little')
    return data[1], data[2], data[5:-4]


def clopper_pearson(failures, shots):
    low = 0.0 if failures == 0 else float(beta.ppf(0.025, failures, shots - failures + 1))
    high = 1.0 if failures == shots else float(beta.ppf(0.975, failures + 1, shots - failures))
    return low, high


def expected_frontier_cycles(width, operations, syndrome):
    if syndrome == 0:
        return 1
    groups = 1 << (max(width, 2) - 2)
    return groups + operations * (2 + 6 * groups) + 2


def verify_and_plot(work, output_dir):
    corpus = work / 'corpus'
    manifest = json.loads((corpus / 'manifest.json').read_text())
    rows = []
    latency_rows = []
    total_decode_frames = 0
    total_transactions = 0
    for entry in manifest['points']:
        name = entry['name']
        point = json.loads((corpus / f'{name}.json').read_text())
        npz = np.load(corpus / f'{name}-shots.npz')
        truths = npz['truth'].astype(int)
        syndromes = [int(s, 16) for s in npz['syndromes']]
        assert len(truths) == len(syndromes) == point['shots']
        maps = {}
        cycles_maps = {}
        for decoder, version in (('uf', 2), ('matching', 0xD505)):
            wire = json.loads((work / decoder / f'{name}-wire.json').read_text())
            results = json.loads((work / decoder / f'{name}-results.json').read_text())
            decoded = {}
            cycles_by_s = {}
            last_crc = None
            for tx_row in wire['transactions']:
                total_transactions += 1
                seq, op, tx = parse_frame(tx_row['tx_hex'], 0xD4)
                rseq, status, rx = parse_frame(tx_row['rx_hex'], 0x4D)
                assert seq == rseq and status == 0, (decoder, name, seq, status)
                if op == 1:
                    if decoder == 'uf':
                        words = struct.unpack('<15I', rx)
                        assert words[0] == version
                    else:
                        words = struct.unpack('<17I', rx)
                        assert words[0] == version
                        last_crc = words[15] | (words[16] << 16)
                elif op == 5:
                    total_decode_frames += 1
                    pred, cycles, err = struct.unpack('<IIB', rx)
                    assert not err and cycles > 0 and pred in (0, 1)
                    s = int.from_bytes(tx, 'little')
                    assert s not in decoded
                    assert pred == point['references'][str(s)][decoder]
                    if decoder == 'matching':
                        assert cycles == expected_frontier_cycles(point['width'], point['operations'], s)
                    decoded[s] = pred
                    cycles_by_s[s] = cycles
            if decoder == 'matching':
                assert last_crc == point['program_crc']
            assert len(decoded) == len(point['unique_syndromes']) == len(results['syndromes'])
            for r in results['syndromes']:
                s = int(r['syndrome'], 16)
                assert decoded[s] == r['prediction'] and cycles_by_s[s] == r['cycles']
            maps[decoder] = decoded
            cycles_maps[decoder] = cycles_by_s

        uf_fail = np.array([maps['uf'][s] != t for s, t in zip(syndromes, truths)], dtype=bool)
        mw_fail = np.array([maps['matching'][s] != t for s, t in zip(syndromes, truths)], dtype=bool)
        for decoder, failed in (('UF', uf_fail), ('Matching', mw_fail)):
            key = 'uf' if decoder == 'UF' else 'matching'
            failures = int(failed.sum())
            low, high = clopper_pearson(failures, point['shots'])
            shot_cycles = [cycles_maps[key][s] for s in syndromes]
            rows.append(dict(
                basis=point['basis'], distance=point['distance'], p=point['p'],
                decoder=decoder, shots=point['shots'], unique_board_syndromes=len(maps[key]),
                failures=failures, failure_probability=failures / point['shots'],
                ci_low=low, ci_high=high,
                mean_cycles=statistics.mean(shot_cycles),
                median_cycles=statistics.median(shot_cycles),
                max_cycles=max(shot_cycles),
                uf_only_failures=int(np.sum(uf_fail & ~mw_fail)),
                matching_only_failures=int(np.sum(mw_fail & ~uf_fail)),
            ))
            latency_rows.append(rows[-1])

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                         'axes.spines.right': False, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.4), sharey=True)
    colors = {3: '#176eaa', 5: '#c26425'}
    series = ((3, 'Matching', '--', 's'), (5, 'Matching', '--', 's'),
              (3, 'UF', '-', 'o'), (5, 'UF', '-', 'o'))
    for ax, basis in zip(axes, ('X', 'Z')):
        for distance, decoder, style, marker in series:
            pts = [r for r in rows if r['basis'] == basis and r['distance'] == distance and r['decoder'] == decoder]
            x = np.array([r['p'] for r in pts])
            y = np.array([r['failure_probability'] for r in pts])
            low = np.array([r['ci_low'] for r in pts])
            high = np.array([r['ci_high'] for r in pts])
            pos = y > 0
            ax.plot(x, np.where(pos, y, np.nan), style, color=colors[distance],
                    marker=marker, markersize=4.5, label=f'{decoder} d={distance}')
            ax.errorbar(x[pos], y[pos], yerr=[y[pos] - low[pos], high[pos] - y[pos]],
                        fmt='none', ecolor=colors[distance], capsize=2, alpha=0.65)
            if (~pos).any():
                ax.scatter(x[~pos], high[~pos], marker='v', color=colors[distance])
        ax.set(xscale='log', yscale='log', xlabel='Physical noise parameter p',
               title=f'Rotated memory {basis}')
        ax.grid(True, which='major', alpha=0.2)
        ax.legend(fontsize=9.5, loc='upper left')
    axes[0].set_ylabel('Logical failure probability per shot')
    fig.suptitle('Zybo Z7-10 FPGA decoders: exact weighted matching vs ordered UF', fontsize=14.5, y=0.98)
    fig.text(0.5, 0.02,
             'All 4 curves decoded in Zybo PL at 100 MHz (93,500 verified UART decode replies across 46,750 unique syndromes)\n'
             '3 extraction rounds · d=3: 8,000 shared shots/point, d=5: 1,500 shared shots/point · 95% exact binomial intervals · ▼ 0 failures upper limit',
             ha='center', fontsize=9.5)
    fig.tight_layout(rect=(0, 0.095, 1, 0.93))
    for suffix in ('png', 'svg'):
        fig.savefig(output_dir / f'benchmark-accuracy.{suffix}', dpi=190, facecolor='white')
    plt.close(fig)
    summary = dict(verified_decode_frames=total_decode_frames,
                   verified_transactions=total_transactions,
                   rows=rows)
    (output_dir / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    import sys
    out = verify_and_plot(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(dict(verified_decode_frames=out['verified_decode_frames'],
                          verified_transactions=out['verified_transactions'],
                          series=len(out['rows']) // 6), indent=2))

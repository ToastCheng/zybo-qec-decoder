#!/usr/bin/env python3
"""Sample real Stim memories and compare ordered UF with weighted PyMatching.

Run from any directory; no serial connection or board programming is performed.
See docs/benchmark-accuracy.md for the experiment contract.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "build/accuracy/matplotlib"))
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pymatching
from scipy.stats import beta
import stim

from qec.surface.circuit import compile_circuit
from qec.surface.decoder import decode


def binomial_interval(failures, shots):
    """Two-sided 95% Clopper-Pearson interval, including exact endpoints."""
    if not 0 <= failures <= shots or shots <= 0:
        raise ValueError("require 0 <= failures <= shots and positive shots")
    low = 0.0 if failures == 0 else float(beta.ppf(.025, failures, shots - failures + 1))
    high = 1.0 if failures == shots else float(beta.ppf(.975, failures + 1, shots - failures))
    return low, high


def plot_results(rows, output, *, include_mwpm=True):
    """Draw per-shot failure probabilities; zero estimates use upper-limit markers."""
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.3), sharey=True)
    colors = {3: "#176eaa", 5: "#c26425"}
    decoders = (("UF", "-", "o"), ("MWPM", "--", "s")) if include_mwpm else (("UF", "-", "o"),)
    for ax, basis in zip(axes, ("X", "Z")):
        for distance in (3, 5):
            for decoder, style, marker in decoders:
                points = [r for r in rows if r["basis"] == basis
                          and r["distance"] == distance and r["decoder"] == decoder]
                x = np.array([r["p"] for r in points])
                y = np.array([r["failure_probability"] for r in points])
                low = np.array([r["ci_low"] for r in points])
                high = np.array([r["ci_high"] for r in points])
                positive = y > 0
                ax.plot(x, np.where(positive, y, np.nan), style, color=colors[distance],
                        marker=marker, markersize=4, label=f"{'Matching' if decoder == 'MWPM' else decoder} d={distance}" if include_mwpm else f"d={distance}")
                ax.errorbar(x[positive], y[positive],
                            yerr=[y[positive] - low[positive], high[positive] - y[positive]],
                            fmt="none", ecolor=colors[distance], capsize=2, alpha=.65)
                if (~positive).any():
                    ax.scatter(x[~positive], high[~positive], marker="v", color=colors[distance])
        ax.set(xscale="log", yscale="log", xlabel="Physical noise parameter p",
               title=f"Rotated memory {basis}")
        ax.grid(True, which="major", alpha=.2)
        ax.legend(fontsize=9, loc="upper left")
    axes[0].set_ylabel("Logical failure probability per shot")
    shots = rows[0]["shots"]
    title = "Ordered unweighted UF vs weighted PyMatching" if include_mwpm else "Ordered unweighted UF"
    fig.suptitle(title, fontsize=15, y=.98)
    fig.text(.5, .025, f"3 extraction rounds · {shots:,} shared shots / point · 95% exact binomial intervals\n"
             "All four Stim noise parameters = p · ▼ zero failures: upper 95% limit · software experiment",
             ha="center", fontsize=10)
    fig.tight_layout(rect=(0, .105, 1, .93))
    for suffix in ("png", "svg"):
        fig.savefig(output / f"benchmark-accuracy.{suffix}", dpi=190, facecolor="white")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New raw-results directory (must not already exist)")
    parser.add_argument("--shots", type=int, default=30000)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261119)
    parser.add_argument("--p", type=float, nargs="+", default=[.001, .002, .004, .008, .016, .032])
    parser.add_argument("--png", type=Path, help="Optional maintained PNG destination")
    parser.add_argument("--readme-png", type=Path, help="Optional four-curve UF/matching README PNG destination")
    args = parser.parse_args()
    if args.shots < 1 or args.batch_size < 1 or args.seed < 0 or args.seed >= 2**64 - 24:
        parser.error("invalid shots, batch size or seed")
    if any(not 0 < p <= .75 for p in args.p) or len(set(args.p)) != len(args.p):
        parser.error("noise points must be distinct and in (0, .75]")
    if args.seed + 4 * len(args.p) >= 2**64:
        parser.error("derived seeds exceed uint64")
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    start = time.perf_counter()
    git = lambda *cmd: subprocess.check_output(["git", "-C", str(ROOT), *cmd], text=True)
    metadata = {
        "schema_version": 1, "utc_started": datetime.now(timezone.utc).isoformat(),
        "command": sys.argv, "source_revision": git("rev-parse", "HEAD").strip(),
        "git_status": git("status", "--short"), "python": sys.version,
        "platform": platform.platform(), "machine": platform.machine(),
        "versions": {name: importlib.metadata.version(name) for name in
                     ("stim", "pymatching", "numpy", "scipy", "matplotlib")},
        "shots_per_point": args.shots, "batch_size": args.batch_size,
        "base_seed": args.seed, "p_grid": sorted(args.p), "rounds": 3,
        "truth": "Stim sampled observable flips; UF errors count as failures",
        "interval": "95% two-sided Clopper-Pearson; marginal, not paired difference",
        "noise_parameters": ["after_clifford_depolarization", "before_round_data_depolarization",
                             "after_reset_flip_probability", "before_measure_flip_probability"],
        "sampling": "fresh sampler per point; sequential calls of batch_size then remainder",
        "reference": "Weighted PyMatching, enable_correlations=False, regenerated per p",
        "execution": "software UF reference; not FPGA execution or timing evidence",
        "points": [],
    }
    sources = ("scripts/benchmark_accuracy.py", "qec/surface/circuit.py",
               "qec/surface/decoder.py", "qec/surface/graph.py")
    for name in sources:
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (output / "source-diff.patch").write_text(git("diff", "HEAD", "--", *sources))
    rows = []
    index = 0
    for basis in ("X", "Z"):
        for distance in (3, 5):
            for p in sorted(args.p):
                seed = args.seed + index
                index += 1
                name = f"memory-{basis.lower()}-d{distance}-p{p:g}"
                circuit = stim.Circuit.generated(
                    f"surface_code:rotated_memory_{basis.lower()}", distance=distance,
                    rounds=3, **{key: p for key in metadata["noise_parameters"]})
                compiled = compile_circuit(str(circuit))
                (output / f"{name}.stim").write_text(str(circuit))
                (output / f"{name}.dem").write_text(compiled["dem"])
                (output / f"{name}-graph.json").write_text(json.dumps(compiled["edges"]))
                matching = pymatching.Matching.from_detector_error_model(stim.DetectorErrorModel(compiled["dem"]))
                matching.ensure_num_fault_ids(circuit.num_observables)
                sampler = circuit.compile_detector_sampler(seed=seed)
                dets, truths, uf_predictions, uf_errors, mw_predictions = [], [], [], [], []
                for offset in range(0, args.shots, args.batch_size):
                    batch = min(args.batch_size, args.shots - offset)
                    detectors, truth = sampler.sample(batch, separate_observables=True)
                    packed = np.packbits(detectors, axis=1, bitorder="little")
                    results = [decode(circuit.num_detectors, compiled["edges"],
                                      int.from_bytes(shot.tobytes(), "little")) for shot in packed]
                    dets.append(packed)
                    truths.append(truth[:, 0])
                    uf_predictions.extend(result["prediction"] for result in results)
                    uf_errors.extend(result["error"] for result in results)
                    mw_predictions.append(matching.decode_batch(detectors)[:, 0])
                truth = np.concatenate(truths).astype(bool)
                uf_prediction = np.array(uf_predictions, dtype=np.uint32)
                errors = np.array(uf_errors, dtype=bool)
                mw_prediction = np.concatenate(mw_predictions).astype(bool)
                uf_failed = errors | (uf_prediction != truth)
                mw_failed = mw_prediction != truth
                np.savez_compressed(output / f"{name}-shots.npz", detectors=np.concatenate(dets),
                                    truth=truth, uf_prediction=uf_prediction, uf_error=errors,
                                    mwpm_prediction=mw_prediction)
                metadata["points"].append({"name": name, "seed": seed, "basis": basis,
                                           "distance": distance, "p": p, "counts": compiled["counts"],
                                           "sha256": compiled["sha256"],
                                           "uf_only_failures": int(np.sum(uf_failed & ~mw_failed)),
                                           "mwpm_only_failures": int(np.sum(mw_failed & ~uf_failed))})
                for decoder, failed in (("UF", uf_failed), ("MWPM", mw_failed)):
                    failures = int(failed.sum())
                    low, high = binomial_interval(failures, args.shots)
                    rows.append({"basis": basis, "distance": distance, "p": p, "decoder": decoder,
                                 "shots": args.shots, "failures": failures,
                                 "uf_errors": int(errors.sum()) if decoder == "UF" else 0,
                                 "failure_probability": failures / args.shots, "ci_low": low, "ci_high": high})
                print(f"{name}: {args.shots} shots, UF={int(uf_failed.sum())}, "
                      f"MWPM={int(mw_failed.sum())}, UF errors={int(errors.sum())}", flush=True)
                with (output / "results.csv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
    plot_results(rows, output)
    if args.readme_png:
        readme_output = output / "readme"
        readme_output.mkdir()
        plot_results(rows, readme_output)
        args.readme_png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(readme_output / "benchmark-accuracy.png", args.readme_png)
    metadata["elapsed_seconds"] = time.perf_counter() - start
    metadata["total_sampled_shots"] = args.shots * index
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    hashes = {str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output / "benchmark-accuracy.png", args.png)
    print(json.dumps({"output": str(output), "shots": metadata["total_sampled_shots"],
                      "elapsed_seconds": metadata["elapsed_seconds"]}))


if __name__ == "__main__":
    main()

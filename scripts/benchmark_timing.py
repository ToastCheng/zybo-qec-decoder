"""Reproduce RTL timing sweeps, finite-job queue models and routed resource plots.

Requires Stim, PyMatching, NumPy, Matplotlib and Vivado's simulator. All raw
outputs belong outside the implementation tree; simulator scratch stays in build/.
"""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def prepare(out, shots, seed):
    import stim
    import pymatching
    from qec.surface.decoder import decode
    from qec.surface.graph import checked_graph

    workloads = []
    vectors = ["10"]
    for distance in (3, 5):
        for p in (0.0001, 0.0003, 0.001, 0.003, 0.01):
            circuit = stim.Circuit.generated(
                "surface_code:rotated_memory_z", distance=distance, rounds=3,
                after_clifford_depolarization=p,
                before_round_data_depolarization=p,
                before_measure_flip_probability=p,
                after_reset_flip_probability=p,
            )
            edges, _ = checked_graph(
                circuit.detector_error_model(decompose_errors=True),
                circuit.num_detectors, circuit.num_observables,
            )
            det, obs = circuit.compile_detector_sampler(seed=seed).sample(
                shots, separate_observables=True
            )
            name = f"d{distance}-z-r3-p{p:g}"
            (out / f"{name}.stim").write_text(str(circuit))
            vectors.append(f"{circuit.num_detectors} {len(edges)} {circuit.num_observables} {shots}")
            vectors.extend(f"{a} {b} {mask:08x}" for a, b, mask in edges)
            sampled = []
            for i, (d, o) in enumerate(zip(det, obs)):
                syndrome = sum(int(v) << j for j, v in enumerate(d))
                truth = sum(int(v) << j for j, v in enumerate(o))
                reference = decode(circuit.num_detectors, edges, syndrome)
                assert not reference["error"]
                sampled.append(dict(shot=i, syndrome=syndrome, truth=truth,
                                    prediction=reference["prediction"]))
                vectors.append(f"{syndrome:x} {reference['prediction']:08x} 0")
            dump(out / f"{name}-shots.json", sampled)
            workloads.append(dict(name=name, distance=distance, rounds=3, p=p,
                                  detectors=circuit.num_detectors, edges=edges,
                                  observables=circuit.num_observables, shots=shots))
    (out / "vectors.txt").write_text("\n".join(vectors) + "\n")
    dump(out / "corpus.json", dict(seed=seed, batch_size=shots,
         stim_version=stim.__version__, pymatching_version=pymatching.__version__,
         noise="All four Stim generated-memory noise probabilities equal p",
         workloads=workloads))


def run(args):
    out = args.data.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prepare(out, args.shots, args.seed)
    sources = [ROOT / "fpga/rtl/common/qec_decoder.sv",
               ROOT / "fpga/rtl/tb/tb_decoder.sv", ROOT / "scripts/simulate.py",
               ROOT / "qec/surface/decoder.py", ROOT / "qec/surface/graph.py",
               Path(__file__)]
    for source in sources:
        target = out / "sources" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    commands = []
    for label in ("baseline", "optimized"):
        target = out / label
        target.mkdir()
        build = ROOT / "build/sim" / f"readme-timing-{label}-{uuid.uuid4().hex[:12]}"
        command = [sys.executable, str(ROOT / "scripts/simulate.py"),
                   "--vectors", str(out / "vectors.txt"), "--build-dir", str(build),
                   "--vivado-bin", str(args.vivado_bin)]
        if label == "baseline":
            core = args.study / "evidence/baseline/sources/fpga/rtl/common/qec_decoder.sv"
            shutil.copyfile(core, target / "qec_decoder.sv")
            command.extend(["--core-source", str(target / "qec_decoder.sv")])
        env = dict(os.environ, PYTHONPYCACHEPREFIX=str(ROOT / "build/readme-timing-cache"))
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        (target / "simulation.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"{label} RTL failed: {target / 'simulation.log'}")
        for name in ("profile.csv", "trace.csv", "initiation.csv"):
            shutil.copyfile(build / name, target / name)
        for name in ("qec_soc_utilization.rpt", "qec_soc_timing_summary.rpt", "qec_soc_drc.rpt"):
            shutil.copyfile(args.study / "evidence" / label / name, target / name)
        commands.append(dict(label=label, command=command, build=str(build)))
        print(f"PASS {label} RTL: {target / 'simulation.log'}", flush=True)
    dump(out / "provenance.json", dict(
        revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        tracked_diff=subprocess.check_output(["git", "diff", "--binary"], cwd=ROOT, text=True),
        study=str(args.study.resolve()), commands=commands, board_programmed=False,
        clock_mhz=100, route="Archived full-SoC baseline/optimized routes; no new route"))
    analyze(args)
    dump(out / "SHA256.json", {str(p.relative_to(out)): digest(p)
         for p in sorted(out.rglob("*")) if p.is_file() and p.name != "SHA256.json"})


def queue(costs, interval):
    """Finite FIFO, one nonpreemptive server, no trace repetition or graph I/O."""
    free = 0
    result = []
    for i, latency in enumerate(costs):
        arrival = i * interval
        start = max(arrival, free)
        free = start + latency + 2
        result.append(dict(shot=i, arrival_cycles=arrival, wait_cycles=start-arrival,
                           result_cycles=start+latency, free_cycles=free))
    return result


def resource(folder):
    utilization = (folder / "qec_soc_utilization.rpt").read_text()
    timing = (folder / "qec_soc_timing_summary.rpt").read_text()
    assert "All user specified timing constraints are met." in timing
    values = timing.split("WNS(ns)", 1)[1].splitlines()[2].split()
    assert float(values[0]) >= 0 and float(values[4]) >= 0
    result = {"wns_ns": float(values[0]), "whs_ns": float(values[4])}
    for key, name in (("LUT", "Slice LUTs"), ("FF", "Slice Registers"), ("BRAM36", "Block RAM Tile")):
        match = re.search(r"\| " + re.escape(name) + r"\s*\|\s*([\d.]+)", utilization)
        result[key] = float(match[1])
    return result


def analyze(args):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = args.data.resolve()
    images = args.images.resolve()
    images.mkdir(parents=True, exist_ok=True)
    meta = json.loads((out / "corpus.json").read_text())
    profiles = {label: rows(out / label / "profile.csv") for label in ("baseline", "optimized")}
    assert (out / "baseline/trace.csv").read_bytes() == (out / "optimized/trace.csv").read_bytes()
    for label in profiles:
        for r in rows(out / label / "initiation.csv"):
            assert int(r["acceptance_gap"]) == int(r["latency"]) + 2
    summary = []
    raw_costs = {}
    for g, workload in enumerate(meta["workloads"]):
        truth = json.loads((out / f"{workload['name']}-shots.json").read_text())
        for label, profile in profiles.items():
            selected = [r for r in profile if int(r["graph"]) == g]
            assert len(selected) == workload["shots"] == len(truth)
            for i, (r, t) in enumerate(zip(selected, truth)):
                assert int(r["shot"]) == i
                assert int(r["syndrome"], 16) == t["syndrome"]
                assert int(r["prediction"], 16) == t["prediction"] and int(r["error"]) == 0
                assert sum(int(r[k]) for k in list(r)[6:]) == int(r["cycles"])
            costs = [int(r["cycles"]) for r in selected]
            raw_costs[label, workload["distance"], workload["p"]] = costs
            mean = float(np.mean(costs))
            summary.append(dict(label=label, distance=workload["distance"], p=workload["p"],
                shots=len(costs), empty=sum(t["syndrome"] == 0 for t in truth),
                mean_us=mean/100, p95_us=sorted(costs)[math.ceil(.95*len(costs))-1]/100,
                max_us=max(costs)/100, model_rate_kjobs_s=100000/(mean+2),
                reference_mismatches=0))
    resources = {label: resource(out / label) for label in profiles}
    dump(out / "summary.json", dict(workloads=summary, resources=resources,
         verified_shots_per_core=sum(w["shots"] for w in meta["workloads"])))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .18})
    colors = {"baseline": "#9b625b", "optimized": "#167d9a"}
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for ax, distance in zip(axes, (3, 5)):
        for label in profiles:
            data = [r for r in summary if r["label"] == label and r["distance"] == distance]
            for field, style, statistic in (("mean_us", "-", "mean"), ("p95_us", "--", "p95")):
                ax.plot([r["p"] for r in data], [r[field] for r in data], style,
                        marker="o", color=colors[label], label=f"{label} {statistic}")
        ax.set(xscale="log", yscale="log", xlabel="Circuit noise probability p",
               ylabel="Acceptance → result (µs)", title=f"Distance {distance} · Z memory · 3 rounds")
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Paired RTL latency · 100 MHz · {meta['batch_size']} shots / point")
    fig.tight_layout(rect=(0, .035, 1, .94))
    fig.text(.5, .015, "All four generated-circuit noise rates = p; no UART, graph loading or queue time.", ha="center", fontsize=9)
    fig.savefig(images / "benchmark-latency.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for column, distance in enumerate((3, 5)):
        ax = axes[0, column]
        for label in profiles:
            data = [r for r in summary if r["label"] == label and r["distance"] == distance]
            ax.plot([r["p"] for r in data], [r["model_rate_kjobs_s"] for r in data],
                    "o-", color=colors[label], label=label)
        ax.set(xscale="log", xlabel="Circuit noise probability p", ylabel="Estimated capacity (k jobs/s)",
               title=f"d{distance}: 1 / mean(service), model")
        ax.legend(fontsize=8)
        ax = axes[1, column]
        for label in profiles:
            costs = raw_costs[label, distance, .001]
            for interval, style in ((330, "-"), (1000, "--")):
                modeled = queue(costs, interval)
                target = out / label / f"queue-d{distance}-p0.001-arrival{interval}.csv"
                with target.open("w") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(modeled[0]))
                    writer.writeheader()
                    writer.writerows(modeled)
                ax.plot([r["arrival_cycles"]/100 for r in modeled],
                        [r["wait_cycles"]/100 for r in modeled], style, color=colors[label],
                        label=f"{label}, Δ={interval/100:g} µs")
        ax.set(xlabel="Finite-job arrival time (µs)", ylabel="Modeled queued work / wait (µs)",
               title=f"d{distance}: p = 0.001, {len(costs)} distinct sampled jobs")
        ax.legend(fontsize=7)
    fig.suptitle("Core-only service capacity and finite FIFO backlog — model, not hardware load test")
    fig.tight_layout(rect=(0, .04, 1, .95))
    fig.text(.5, .015, "Service = RTL latency + 2 clocks; one server, infinite FIFO; independent windows, not continuous QEC.", ha="center", fontsize=9)
    fig.savefig(images / "benchmark-backlog.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(10, 4))
    for ax, key, title in zip(axes, ("LUT", "FF", "BRAM36"), ("Slice LUTs", "Flip-flops", "36 Kb RAM tiles")):
        values = [resources[label][key] for label in profiles]
        ax.bar(list(profiles), values, color=list(colors.values()), width=.6)
        ax.set_title(title)
        ax.set_ylim(0, max(values)*1.22)
        for i, value in enumerate(values):
            ax.text(i, value+max(values)*.025, f"{value:g}", ha="center")
    fig.suptitle("Routed full-SoC resource cost · Zybo Z7-10 · 100 MHz")
    fig.tight_layout(rect=(0, .11, 1, .93))
    fig.text(.5, .045, "128 detectors / 512 edges / 32 observables; archived routes, not core-only synthesis.", ha="center", fontsize=9)
    fig.text(.5, .005,
             f"Setup WNS: baseline {resources['baseline']['wns_ns']:+.3f} ns, "
             f"optimized {resources['optimized']['wns_ns']:+.3f} ns. No new route or board measurement.",
             ha="center", fontsize=9)
    fig.savefig(images / "benchmark-resources.png", dpi=180)
    plt.close(fig)
    print(json.dumps(dict(verified_shots_per_core=sum(w["shots"] for w in meta["workloads"]),
                         resources=resources, summary=str(out / "summary.json")), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "plot"))
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--study", type=Path, default=Path("/home/toastcheng/qc-research/fpga-qec/core-scan-study"))
    parser.add_argument("--images", type=Path, default=ROOT / "docs/images")
    parser.add_argument("--vivado-bin", type=Path, default=Path("/home/toastcheng/amd/2025.2/Vivado/bin"))
    parser.add_argument("--shots", type=int, default=256)
    parser.add_argument("--seed", type=int, default=123)
    args = parser.parse_args()
    if args.action == "run":
        run(args)
    else:
        analyze(args)


if __name__ == "__main__":
    main()

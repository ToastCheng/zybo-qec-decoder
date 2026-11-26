"""Compile and run Vivado xsim decoder testbenches in isolated build/sim/ directories.

Supports the `core`, `bridge`, and `counter` testbenches. For the `core` bench,
generates a deterministic graph/syndrome vector file using Python's reference
decoder unless `--vectors` is provided. Saves xvlog/xelab/xsim console logs into
the build directory and requires the bench's `PASS qec <bench>` marker.

Usage:
    python3 scripts/simulate.py [--bench core|bridge|counter] [--build-dir build/sim/<name>]
"""

import argparse
import ast
import random
import shutil
import subprocess
import uuid
from pathlib import Path


def write_vectors(root, build):
    """Generate deterministic edge-case and random test graphs using Python's reference decoder."""
    tree = ast.parse((root / "qec/surface/decoder.py").read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "decode"
    )
    namespace = {}
    # Load only decode() from decoder.py so simulation works without QEC runtime dependencies.
    exec(  # noqa: S102
        compile(ast.Module(body=[function], type_ignores=[]), "decoder.py", "exec"),
        namespace,
    )
    decode = namespace["decode"]
    rng = random.Random(721093)
    graphs = [
        (0, [], 0),
        (1, [(0, 1, 0x80000005)], 32),
        (2, [(0, 1, 3), (1, 2, 2), (0, 2, 1)], 2),
        (3, [(2, 3, 5), (0, 1, 6), (1, 2, 3), (0, 3, 7)], 3),
        (4, [], 0),
        (4, [(0, 1, 9), (2, 3, 3)], 4),
    ]
    for n, m, o in [(8, 16, 32), (1, 1, 1), (5, 12, 0), (17, 35, 17), (128, 512, 32)]:
        pairs = [(a, b) for a in range(n + 1) for b in range(a + 1, n + 1)]
        rng.shuffle(pairs)
        edges = [(a, b, rng.getrandbits(o)) for a, b in pairs[:m]]
        graphs.append((n, edges, o))
    # Reverse chain forces normal decoding to cross the 16-bit cycle-counter boundary.
    graphs.append(
        (128, [(a, a + 1, rng.getrandbits(32)) for a in reversed(range(128))], 32)
    )
    records = [str(len(graphs))]
    total = 0
    for n, edges, o in graphs:
        shots = (
            list(range(1 << n))
            if n <= 8
            else [0, 1, 1 << (n - 1), (1 << n) - 1]
            + [rng.getrandbits(n) for _ in range(40)]
        )
        records.append(f"{n} {len(edges)} {o} {len(shots)}")
        records.extend(f"{a} {b} {mask:08x}" for a, b, mask in edges)
        for shot in shots:
            result = decode(n, edges, shot)
            records.append(
                f"{shot:x} {result['prediction']:08x} {int(result['error'])}"
            )
        total += len(shots)
    (build / "qec_vectors.txt").write_text("\n".join(records) + "\n")
    print(f"Reference corpus: {len(graphs)} graphs, {total} shots", flush=True)


def main():
    """Run the selected Vivado testbench in a private build/sim/ directory.

    Validates CLI flags, generates or copies `qec_vectors.txt` for the `core`
    bench, invokes `xvlog`, `xelab`, and `xsim`, writes per-tool console logs,
    and fails unless the bench prints its `PASS qec <bench>` marker.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bench", choices=("core", "bridge", "counter"), default="core"
    )
    parser.add_argument("--build-dir", default=None)
    parser.add_argument(
        "--vectors",
        type=Path,
        help="Existing core corpus; skips only the long-counter coverage requirement",
    )
    parser.add_argument(
        "--core-source",
        type=Path,
        help="Explicit archived core RTL for reproducible comparisons",
    )
    parser.add_argument(
        "--vivado-bin", default="/home/toastcheng/amd/2025.2/Vivado/bin"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = Path(
        args.build_dir or root / f"build/sim/{args.bench}-{uuid.uuid4().hex[:12]}"
    ).resolve()
    sim_root = (root / "build/sim").resolve()
    if build == sim_root or not build.is_relative_to(sim_root):
        parser.error("--build-dir must be a private directory under build/sim")
    if build.exists() and (not build.is_dir() or any(build.iterdir())):
        parser.error("--build-dir must be new or empty")
    build.mkdir(parents=True, exist_ok=True)
    if args.vectors and args.bench != "core":
        parser.error("--vectors requires --bench core")
    if args.vectors:
        shutil.copyfile(args.vectors, build / "qec_vectors.txt")
    elif args.bench == "core":
        write_vectors(root, build)
    sources = [(args.core_source or root / "fpga/rtl/common/qec_decoder.sv").resolve()]
    if args.bench in ("bridge", "counter"):
        sources.append(root / "fpga/rtl/common/ps_bridge.sv")
    bench_name = "decoder" if args.bench == "core" else args.bench
    sources.append(root / f"fpga/rtl/tb/tb_{bench_name}.sv")
    commands = [
        ["xvlog", "--sv", *map(str, sources)],
        ["xelab", f"tb_{bench_name}", "-s", "qec_sim"],
        ["xsim", "qec_sim", "-runall"],
    ]
    if args.vectors:
        commands[-1].extend(["-testplusarg", "profile_only"])
    text = ""
    for command in commands:
        command[0] = str(Path(args.vivado_bin) / command[0])
        result = subprocess.run(
            command, check=False, cwd=build, capture_output=True, text=True
        )
        text = result.stdout + result.stderr
        (build / f"{Path(command[0]).name}.console.log").write_text(text)
        print(text, end="", flush=True)
        if result.returncode or "Fatal:" in text or "FATAL" in text:
            raise SystemExit(result.returncode or 1)
    if f"PASS qec {args.bench}" not in text:
        raise SystemExit("simulation exited without PASS marker")


if __name__ == "__main__":
    main()

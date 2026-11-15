#!/usr/bin/env python3
"""Run runtime decoder benches with isolated real Vivado simulator products."""
import argparse
import ast
from pathlib import Path
import random
import subprocess


def write_vectors(root, build):
    """Execute the actual reference function without optional Stim imports."""
    tree = ast.parse((root / "qec/surface/decoder.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "decode")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "decoder.py", "exec"), namespace)
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
    # Reverse-ordered long path forces >65535 cycles without fabricating counters.
    graphs.append((128, [(a, a + 1, rng.getrandbits(32)) for a in reversed(range(128))], 32))
    records = [str(len(graphs))]
    total = 0
    for n, edges, o in graphs:
        shots = list(range(1 << n)) if n <= 8 else [0, 1, 1 << (n - 1), (1 << n) - 1] + [rng.getrandbits(n) for _ in range(40)]
        records.append(f"{n} {len(edges)} {o} {len(shots)}")
        records.extend(f"{a} {b} {mask:08x}" for a, b, mask in edges)
        for shot in shots:
            result = decode(n, edges, shot)
            records.append(f"{shot:x} {result['prediction']:08x} {int(result['error'])}")
        total += len(shots)
    (build / "runtime_vectors.txt").write_text("\n".join(records) + "\n")
    print(f"Reference corpus: {len(graphs)} graphs, {total} shots", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", choices=("core", "bridge", "counter"), default="core")
    parser.add_argument("--build-dir", default=None)
    parser.add_argument("--vivado-bin", default="/home/toastcheng/amd/2025.2/Vivado/bin")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = Path(args.build_dir or root / f"build/runtime-{args.bench}").resolve()
    build.mkdir(parents=True, exist_ok=True)
    if args.bench == "core":
        write_vectors(root, build)
    sources = [root / "rtl/common/runtime_surface_decoder.sv"]
    if args.bench in ("bridge", "counter"):
        sources.append(root / "rtl/common/runtime_surface_ps_bridge.sv")
    sources.append(root / f"rtl/tb/tb_runtime_{args.bench}.sv")
    commands = [
        ["xvlog", "--sv", *map(str, sources)],
        ["xelab", f"tb_runtime_{args.bench}", "-s", "runtime_sim"],
        ["xsim", "runtime_sim", "-runall"],
    ]
    text = ""
    for command in commands:
        command[0] = str(Path(args.vivado_bin) / command[0])
        result = subprocess.run(command, cwd=build, capture_output=True, text=True)
        text = result.stdout + result.stderr
        (build / f"{Path(command[0]).name}.console.log").write_text(text)
        print(text, end="", flush=True)
        if result.returncode or "Fatal:" in text or "FATAL" in text:
            raise SystemExit(result.returncode or 1)
    if f"PASS runtime {args.bench}" not in text:
        raise SystemExit("simulation exited without PASS marker")


if __name__ == "__main__":
    main()

# Sorted surface graph, half-edge growth and forest peeling

Companion to [`decoder.py`](decoder.py).

## Contracts and flow

`graph(distance=3, rounds=3, basis="z", noise=0.001)` validates odd distance >=3, positive rounds and x/z basis, then returns a dictionary containing a Stim rotated-memory circuit, counts and sorted `(a,b,observable)` edges. PyMatching's virtual boundary becomes vertex n, where n is the detector count. The graph discards weights for the UF reference; edge order fixes scheduling and ties.

`decode(n, edges, syndrome)` requires a nonnegative syndrome fitting n bits. It initializes a cluster per detector plus boundary, then sweeps edges. Odd nonboundary roots grow half-edges; saturation at two joins clusters, always preferring boundary or otherwise the lower root ID. Unions relabel every vertex, collect a forest and update degrees. The bounded growth loop can return `error=True`.

Peeling chooses the lowest nonboundary leaf and first sorted incident forest edge. An odd leaf transfers parity to the other endpoint, XORs the edge observable into prediction, and records its edge index. Boundary is deliberately never peeled. The result dictionary contains `prediction`, `error` and `correction_edges`; correction indices refer to the original edge ordering. Cancelling detector parity does not prove the logical prediction is correct. Observable labels may be integer masks for compiler-generated multibit software graphs.

`export(g, target)` writes `.mem` and `.json` beside a stem. With vb=n.bit_length(), each ROM word is `a | b<<vb | obs<<(2*vb)`. Metadata includes hash and library versions. Storage is O(V+E), but repeated relabel/leaf scans are not optimized near-linear union-find and are not a constant-latency claim.

## Callable index

- `graph` — Return a sorted graph and Stim circuit for an odd-distance rotated X/Z memory experiment.
- `decode` — Deterministic serial half-edge growth, relabel unions, forest peeling.
- `export` — Write packed edge ROM and hashed graph metadata beside the supplied target stem.

## Usage and verification

Run from the repository root using the configured Python environment (for example `qec/.venv/bin/python` in place of `python`).

```sh
python -c "from qec.surface.decoder import graph, decode; g=graph(); print(decode(g['detectors'], g['edges'], 0))"
python -m pytest -q qec/tests/test_surface.py
```

Help-only commands intentionally avoid hardware I/O; physical entry points require explicit authorization and matching prebuilt artifacts before actual capture.

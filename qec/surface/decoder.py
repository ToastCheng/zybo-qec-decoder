"""Software reference decoder using unweighted Union-Find and forest peeling.

Decodes packed detector syndromes on the unweighted graphs produced by
``qec.surface.circuit`` and ``qec.surface.graph``. Used for standalone software
runs and to cross-check FPGA hardware predictions in ``run.py``.
"""


def decode(n, edges, syndrome):
    """Decode a packed syndrome on an unweighted graph with ``n`` detectors.

    Vertices ``0`` through ``n - 1`` are detectors, and vertex ``n`` is the
    shared boundary, which absorbs odd-parity clusters without driving further
    growth. ``syndrome`` is a little-endian integer bitmask where bit ``i`` is
    detector ``i``. Each entry in ``edges`` is an ``(a, b, mask)`` triple
    joining vertices ``a`` and ``b``, with bit ``i`` of ``mask`` marking
    logical observable ``L_i``.

    To match the FPGA core bit-for-bit, cluster growth sweeps ``edges`` in
    input order (merging into the boundary vertex ``n`` first, or otherwise the
    smaller cluster root), and forest peeling always removes the lowest-index
    degree-1 detector leaf via its lowest-index incident forest edge. Keeping
    this edge and leaf order ensures ties break identically in software and
    hardware.

    Returns a dictionary with:
    - ``prediction``: XOR of the observable masks of all selected correction
      edges.
    - ``correction_edges``: input indices of the selected edges in peeling
      order.
    - ``error``: ``True`` if growth did not neutralize all odd-parity clusters
      within ``2 * (n + 1)`` sweeps, if peeling stalled on a cycle with no
      detector leaves, or if any detector parity remains nonzero at the end.

    Raises ``ValueError`` if ``syndrome`` is negative or has bits at or above
    position ``n``.
    """
    if syndrome < 0 or syndrome >> n:
        raise ValueError("syndrome does not fit graph")
    # Vertex n is the shared boundary; once a cluster reaches it, it stops growing.
    labels = list(range(n + 1))
    parity = [(syndrome >> i) & 1 for i in range(n)] + [0]
    growth = [0] * len(edges)
    forest = set()
    degree = [0] * (n + 1)

    # Phase 1: grow odd-parity clusters in input edge order until all are neutral.
    for sweep in range(2 * (n + 1)):
        if not any(parity[:n]):
            break
        for i, (a, b, _) in enumerate(edges):
            ra, rb = labels[a], labels[b]
            active = int(ra != n and parity[ra] != 0) + int(rb != n and parity[rb] != 0)
            if ra == rb or not active:
                continue
            growth[i] = min(2, growth[i] + active)
            if growth[i] < 2:
                continue

            # Prefer the boundary root on merges, otherwise the lower vertex index.
            winner = n if n in (ra, rb) else min(ra, rb)
            loser = rb if winner == ra else ra
            parity[winner] = parity[ra] ^ parity[rb]
            parity[loser] = 0
            labels = [winner if r == loser else r for r in labels]
            forest.add(i)
            degree[a] += 1
            degree[b] += 1
    else:
        return {"prediction": 0, "error": True, "correction_edges": []}
    # Phase 2: peel the spanning forest from lowest-index degree-1 detector leaves.
    work = [(syndrome >> i) & 1 for i in range(n)] + [0]
    prediction = 0
    correction = []
    while forest:
        leaves = [i for i in range(n) if degree[i] == 1]
        if not leaves:
            return {
                "prediction": prediction,
                "error": True,
                "correction_edges": correction,
            }
        leaf = leaves[0]
        e = next(i for i in sorted(forest) if leaf in edges[i][:2])
        a, b, obs = edges[e]
        other = b if a == leaf else a
        if work[leaf]:
            work[other] ^= 1
            prediction ^= obs
            correction.append(e)
        work[leaf] = 0
        degree[a] -= 1
        degree[b] -= 1
        forest.remove(e)
    return {
        "prediction": prediction,
        "error": any(work[:n]),
        "correction_edges": correction,
    }

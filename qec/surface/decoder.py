"""Decode an unweighted graph with ordered growth and forest peeling."""


def decode(n, edges, syndrome):
    """Match RTL tie order: input edges for growth, then lowest-index leaves."""
    if syndrome < 0 or syndrome >> n:
        raise ValueError("syndrome does not fit graph")
    # Vertex n is the boundary; its cluster does not drive further growth.
    labels = list(range(n + 1))
    parity = [(syndrome >> i) & 1 for i in range(n)] + [0]
    growth = [0] * len(edges)
    forest = set()
    degree = [0] * (n + 1)

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

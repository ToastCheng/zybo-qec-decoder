"""Pack disconnected detector components into exact hardware-sized windows."""


def partition_graph(detectors, edges, *, max_detectors, max_edges):
    """Never cut a detector-to-detector edge or change observable labels."""
    if detectors <= max_detectors and len(edges) <= max_edges:
        return [{"indices": list(range(detectors)), "edges": list(edges)}]
    roots = list(range(detectors))

    def root(vertex):
        while roots[vertex] != vertex:
            roots[vertex] = roots[roots[vertex]]
            vertex = roots[vertex]
        return vertex

    for a, b, _ in edges:
        if a != detectors and b != detectors:
            ra, rb = root(a), root(b)
            roots[max(ra, rb)] = min(ra, rb)
    vertices = {}
    for vertex in range(detectors):
        vertices.setdefault(root(vertex), []).append(vertex)
    component_edges = {r: [] for r in vertices}
    for edge in edges:
        a, b, _ = edge
        component_edges[root(b if a == detectors else a)].append(edge)
    groups = []
    current = []
    count = 0
    edge_count = 0
    for r, indices in vertices.items():
        number_edges = len(component_edges[r])
        if len(indices) > max_detectors or number_edges > max_edges:
            raise ValueError(
                "A connected component exceeds FPGA capacities: "
                f"{len(indices)} detectors, {number_edges} edges; "
                f"image supports {max_detectors}/{max_edges}"
            )
        if current and (
            count + len(indices) > max_detectors
            or edge_count + number_edges > max_edges
        ):
            groups.append(current)
            current, count, edge_count = [], 0, 0
        current.append(r)
        count += len(indices)
        edge_count += number_edges
    if current:
        groups.append(current)
    chunks = []
    for group in groups:
        indices = sorted(v for r in group for v in vertices[r])
        mapping = {v: i for i, v in enumerate(indices)}
        mapping[detectors] = len(indices)
        chosen = set(group)
        local_edges = [
            (mapping[a], mapping[b], mask)
            for a, b, mask in edges
            if root(b if a == detectors else a) in chosen
        ]
        chunks.append({"indices": indices, "edges": local_edges})
    return chunks


def decode_chunks(board, chunks, observables, syndrome):
    """XOR independent FPGA predictions; sum only measured per-window core cycles."""
    prediction = 0
    cycles = 0
    measured = []
    loaded = None
    for chunk in chunks:
        indices = chunk["indices"]
        local = sum(((syndrome >> vertex) & 1) << i for i, vertex in enumerate(indices))
        loaded = board.load_graph(len(indices), chunk["edges"], observables)
        answer = board.decode(local)
        if (
            getattr(answer, "decode_error", False)
            or answer.cycles <= 0
            or not 0 <= answer.prediction < 2**observables
        ):
            raise OSError(
                "FPGA returned invalid component prediction/cycles/decode_error"
            )
        prediction ^= answer.prediction
        cycles += answer.cycles
        measured.append(
            {
                "indices": indices,
                "edges": chunk["edges"],
                "syndrome": local,
                "prediction": answer.prediction,
                "cycles": answer.cycles,
            }
        )
    if loaded is None:
        raise ValueError("No detector windows to decode")
    return {
        "prediction": prediction,
        "cycles": cycles,
        "identity": list(loaded.words),
        "hardware_chunks": measured,
    }

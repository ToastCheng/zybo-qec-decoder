"""Partition large decoding graphs into FPGA-sized windows and decode them.

When a compiled surface-code graph exceeds the FPGA's detector or edge
capacity, ``run.py`` uses this module to pack disconnected detector components
into hardware-sized windows and decode them sequentially through
``GraphDecoder``.
"""


def partition_graph(detectors, edges, *, max_detectors, max_edges):
    """Pack whole connected detector components into FPGA-sized windows.

    Vertex ``detectors`` is the shared boundary and is ignored when finding
    connected components. Because the boundary absorbs clusters without
    propagating growth across it, disconnected detector subgraphs (such as
    separate X and Z components in a CSS code) can be decoded independently
    without changing the clusters or final correction.

    If the entire graph already fits within ``max_detectors`` and
    ``max_edges``, this returns a single window with the original detectors and
    edges. Otherwise it packs whole components into windows that fit both
    limits. Each window dictionary holds:
    - ``indices``: sorted global detector indices in local bit order.
    - ``edges``: ``(local_a, local_b, mask)`` triples remapped to the window's
      local vertex numbering, with its boundary vertex at ``len(indices)``.

    Input edge order and global observable masks are preserved in every window
    so hardware tie-breaking and final XOR combination match a full-graph
    decode. Raises ``ValueError`` if any single connected component exceeds
    ``max_detectors`` or ``max_edges``.
    """
    if detectors <= max_detectors and len(edges) <= max_edges:
        return [{"indices": list(range(detectors)), "edges": list(edges)}]
    roots = list(range(detectors))

    def root(vertex):
        """Find the union-find root of ``vertex`` using path halving."""
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
    """Upload and decode each graph window on the FPGA, then combine results.

    For each window produced by ``partition_graph``, this packs the window's
    detector bits from the global ``syndrome`` into local bit order, uploads
    the local graph via ``board.load_graph``, and runs ``board.decode``.
    Because each window carries global observable masks and represents
    independent components, XORing the per-window predictions yields the full
    logical prediction.

    Returns a dictionary with:
    - ``prediction``: XOR of all per-window logical predictions.
    - ``cycles``: sum of measured FPGA core decode cycles across all windows
      (excluding graph uploads and UART transport).
    - ``identity``: raw identity words reported by the final graph load.
    - ``hardware_chunks``: list of per-window dicts with ``indices``,
      ``edges``, local ``syndrome``, ``prediction``, and ``cycles``.

    Raises ``ValueError`` if ``chunks`` is empty, and ``OSError`` if the board
    reports a decode error, a non-positive cycle count, or a prediction outside
    ``0 .. 2**observables - 1``.
    """
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

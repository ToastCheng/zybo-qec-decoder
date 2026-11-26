"""Tests for `qec.surface.partition`, which splits only disconnected detector components across hardware windows."""

import importlib.util

import pytest


def api():
    """Import and return `partition_graph` after verifying the partition module exists."""
    assert importlib.util.find_spec("qec.surface.partition"), (
        "missing exact graph partitioner"
    )
    from qec.surface.partition import partition_graph

    return partition_graph


def test_disconnected_components_keep_boundary_and_global_observable_bits():
    """Disconnected components split cleanly and reproduce exact decoding across all 16 syndromes."""
    split = api()
    edges = [(0, 1, 1), (1, 4, 1), (2, 3, 2), (3, 4, 2)]
    chunks = split(4, edges, max_detectors=2, max_edges=2)
    assert chunks == [
        {"indices": [0, 1], "edges": [(0, 1, 1), (1, 2, 1)]},
        {"indices": [2, 3], "edges": [(0, 1, 2), (1, 2, 2)]},
    ]
    from qec.surface.decoder import decode

    for syndrome in range(16):
        expected = decode(4, edges, syndrome)
        prediction = 0
        error = False
        for chunk in chunks:
            local = sum(
                ((syndrome >> global_id) & 1) << i
                for i, global_id in enumerate(chunk["indices"])
            )
            result = decode(len(chunk["indices"]), chunk["edges"], local)
            prediction ^= result["prediction"]
            error |= result["error"]
        assert (prediction, error) == (expected["prediction"], expected["error"])


def test_partition_rejects_connected_component_instead_of_cutting_edges():
    """A connected component larger than window capacity raises ValueError instead of cutting edges."""
    with pytest.raises(ValueError, match="connected component"):
        api()(3, [(0, 1, 0), (1, 2, 0)], max_detectors=2, max_edges=4)


def test_partition_keeps_original_indices_and_order_if_it_fits():
    """Graphs that fit in a single window keep their original detector indices and edge order."""
    edges = [(2, 3, 1), (0, 1, 2), (1, 3, 0)]
    assert api()(3, edges, max_detectors=3, max_edges=3) == [
        {"indices": [0, 1, 2], "edges": edges}
    ]

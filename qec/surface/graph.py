"""Validate a Stim detector error model and project it to an unweighted graph.

Called by ``qec.surface.circuit.compile_circuit`` right after Stim builds a
detector error model (DEM). This module checks that every fault component is
graphlike and unambiguous before producing the edge list and PyMatching graph
used downstream by the software decoder, window partitioner, and FPGA host.
"""


def checked_graph(dem, detectors, observables):
    """Convert a Stim DEM into sorted unweighted edges and a PyMatching graph.

    Returns ``(edges, matching)``, where ``edges`` is a sorted list of
    ``(a, b, mask)`` tuples with ``0 <= a < b <= detectors``. A component that
    triggers only one detector connects to the reserved boundary vertex
    ``detectors``, and bit ``i`` of ``mask`` is set when the edge flips Stim
    logical observable ``L_i``. Passing ``observables`` ensures ``matching``
    keeps the full logical observable width even if no edge carries a flip.

    Every separator-delimited component in the flattened DEM is checked before
    projection so PyMatching cannot silently drop or merge faults. Raises
    ``ValueError`` for out-of-range detector or observable indices, hyperedges
    (more than two detectors), detectorless logical errors, conflicting
    observable masks on the same endpoint pair, or any mismatch between the DEM
    signatures and the edges PyMatching produces.
    """
    import pymatching
    import stim

    signatures = {}
    for instruction in dem.flattened():
        if instruction.type != "error":
            continue
        ds, mask = set(), 0
        # Append a separator so the final component runs through the same checks.
        for target in instruction.targets_copy() + [stim.target_separator()]:
            if target.is_separator():
                if not ds and mask:
                    raise ValueError(
                        "detectorless logical component cannot be represented"
                    )
                if len(ds) > 2:
                    raise ValueError("non-graphlike component cannot be represented")
                if ds:
                    endpoints = tuple(
                        sorted(ds | ({detectors} if len(ds) == 1 else set()))
                    )
                    if endpoints in signatures and signatures[endpoints] != mask:
                        raise ValueError(
                            "ambiguous endpoint observable masks cannot be represented"
                        )
                    signatures[endpoints] = mask
                ds, mask = set(), 0
            elif target.is_relative_detector_id():
                if not 0 <= target.val < detectors:
                    raise ValueError("detector index outside graph")
                ds.symmetric_difference_update([target.val])
            elif target.is_logical_observable_id():
                if not 0 <= target.val < observables:
                    raise ValueError("observable index outside graph")
                mask ^= 1 << target.val
    matching = pymatching.Matching.from_detector_error_model(dem)
    matching.ensure_num_fault_ids(observables)
    edges = sorted(
        (
            min(a, detectors if b is None else b),
            max(a, detectors if b is None else b),
            sum(1 << i for i in data["fault_ids"]),
        )
        for a, b, data in matching.edges()
    )
    expected = sorted((a, b, mask) for (a, b), mask in signatures.items())
    if edges != expected:
        raise ValueError("PyMatching graph projection lost or changed DEM components")
    return edges, matching

"""Check DEM components before converting them to graph edges."""


def checked_graph(dem, detectors, observables):
    """Reject hyperedges, detectorless logical faults and conflicting endpoint masks."""
    import pymatching
    import stim

    signatures = {}
    for instruction in dem.flattened():
        if instruction.type != "error":
            continue
        ds, mask = set(), 0
        # A trailing separator applies the same checks to the final component.
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

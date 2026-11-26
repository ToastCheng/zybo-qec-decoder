"""Tests verifying the worked decoder graph examples from the design guide."""

from qec.surface.decoder import decode


def test_design_guide_pairs_two_detectors():
    """Check that two active defects pair along edges [0, 1] and flip observable 0."""
    edges = [(0, 1, 1), (1, 2, 0), (2, 3, 2)]
    result = decode(3, edges, 0b101)
    assert result == {
        "prediction": 0b01,
        "error": False,
        "correction_edges": [0, 1],
    }


def test_design_guide_pairs_one_detector_to_boundary():
    """Check that a single defect pairs to the boundary along edge 2 and flips observable 1."""
    edges = [(0, 1, 1), (1, 2, 0), (2, 3, 2)]
    result = decode(3, edges, 0b100)
    assert result == {
        "prediction": 0b10,
        "error": False,
        "correction_edges": [2],
    }

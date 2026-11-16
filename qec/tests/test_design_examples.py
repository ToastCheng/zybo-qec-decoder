"""Keep the design guide's worked graph examples executable."""

from qec.surface.decoder import decode


def test_design_guide_pairs_two_detectors():
    edges = [(0, 1, 1), (1, 2, 0), (2, 3, 2)]
    result = decode(3, edges, 0b101)
    assert result == {
        "prediction": 0b01,
        "error": False,
        "correction_edges": [0, 1],
    }


def test_design_guide_pairs_one_detector_to_boundary():
    edges = [(0, 1, 1), (1, 2, 0), (2, 3, 2)]
    result = decode(3, edges, 0b100)
    assert result == {
        "prediction": 0b10,
        "error": False,
        "correction_edges": [2],
    }

"""Multiple exact graph windows can share one loaded FPGA image."""

from types import SimpleNamespace

from qec.surface.decoder import decode
from qec.surface.simulation import CircuitExperiment


def test_disconnected_graph_uses_measured_component_decodes(monkeypatch):
    loads = []

    class Board:
        def __init__(self, port):
            self.transactions = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def identity(self):
            return SimpleNamespace(
                max_detectors=2, max_edges=2, max_observables=32, words=(2, 2, 2, 32)
            )

        def load_graph(self, n, edges, obs):
            self.n, self.edges = n, edges
            loads.append((n, edges, obs))
            return self.identity()

        def decode(self, syndrome):
            answer = decode(self.n, self.edges, syndrome)
            assert not answer["error"]
            self.transactions.append({"opcode": 5, "tx": b"tx", "rx": b"rx"})
            return SimpleNamespace(prediction=answer["prediction"], cycles=7)

    monkeypatch.setattr("qec.surface.simulation.GraphDecoder", Board)
    cfg = {
        "circuit": "R 0 1 2\nX_ERROR(1) 0 1 2\nM 0 1 2\nDETECTOR rec[-3]\nDETECTOR rec[-2]\nDETECTOR rec[-1]\nOBSERVABLE_INCLUDE(0) rec[-3]\nOBSERVABLE_INCLUDE(1) rec[-2]\nOBSERVABLE_INCLUDE(2) rec[-1]",
        "reference": None,
        "seed": 1,
        "added_noise": 0,
    }
    result = CircuitExperiment("TEST-DEVICE").run(cfg)
    assert result["prediction"] == result["observable_truth"] == 7
    assert result["cycles"] == 14
    assert [n for n, _, _ in loads] == [2, 1]
    assert [chunk["cycles"] for chunk in result["hardware_chunks"]] == [7, 7]
    assert result["hardware_chunks"][1]["indices"] == [2]
    from qec.surface.run import run_circuit

    loads.clear()
    summary = run_circuit(
        cfg["circuit"], shots=2, seed=1, port="TEST-DEVICE", decoder_factory=Board
    )
    assert summary["shots"] == 2
    assert summary["logical_failures"] == summary["reference_mismatches"] == 0
    assert [n for n, _, _ in loads] == [2, 1, 2, 1]

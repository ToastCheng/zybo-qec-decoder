import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import stim

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "qec/examples/phase_bell.stim"


def test_software_run_archives_actual_seeded_shots(tmp_path):
    from qec.surface.run import run_circuit

    source = EXAMPLE.read_text()
    destination = tmp_path / "software"
    summary = run_circuit(source, shots=32, seed=17, out=destination)
    assert summary["source"] == "Software"
    assert summary["shots"] == 32
    assert summary["observables"] == 2
    rows = [
        json.loads(line)
        for line in (destination / "shots.jsonl").read_text().splitlines()
    ]
    ds, os = (
        stim.Circuit(source)
        .compile_detector_sampler(seed=17)
        .sample(32, separate_observables=True)
    )
    for row, d, o in zip(rows, ds, os):
        assert row["syndrome"] == sum(int(v) << i for i, v in enumerate(d))
        assert row["observable"] == sum(int(v) << i for i, v in enumerate(o))
        assert row["cycles"] is None
    assert json.loads((destination / "summary.json").read_text()) == summary
    manifest = json.loads((destination / "manifest.json").read_text())
    assert manifest["seed"] == 17 and manifest["shots"] == 32
    assert manifest["source"] == "Software"
    with pytest.raises(FileExistsError):
        run_circuit(source, shots=32, seed=17, out=destination)


def test_board_failure_archives_partial_evidence_without_success(tmp_path):
    from qec.surface.run import run_circuit

    calls = []

    class TestBoard:
        def __init__(self, port):
            calls.append(("port", port))
            self.transactions = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def identity(self):
            return SimpleNamespace(max_detectors=128, max_edges=512, max_observables=32)

        def load_graph(self, n, edges, obs):
            calls.append(("load", n, len(edges), obs))

        def decode(self, syndrome):
            raise OSError("explicit test device timeout")

        def save_archive(self, path):
            Path(path).write_text(
                json.dumps(
                    {"source": "explicit software test device", "transactions": []}
                )
            )

    destination = tmp_path / "failed"
    with pytest.raises(IOError, match="timeout"):
        run_circuit(
            EXAMPLE.read_text(),
            shots=2,
            seed=1,
            port="test-device",
            out=destination,
            decoder_factory=TestBoard,
        )
    assert calls == [("port", "test-device"), ("load", 2, 2, 2)]
    assert not (destination / "summary.json").exists()
    assert "timeout" in (destination / "error.json").read_text()
    assert (destination / "wire.json").exists()


def test_invalid_request_never_opens_serial(tmp_path):
    from qec.surface.run import run_circuit

    def forbidden(port):
        pytest.fail("invalid input reached serial")

    for options in [{"shots": 0}, {"seed": -1}, {"shots": True}]:
        with pytest.raises(ValueError):
            run_circuit(
                EXAMPLE.read_text(),
                port="forbidden",
                decoder_factory=forbidden,
                **options,
            )
    with pytest.raises(ValueError):
        run_circuit(
            "H 0\nM 0\nDETECTOR rec[-1]", port="forbidden", decoder_factory=forbidden
        )

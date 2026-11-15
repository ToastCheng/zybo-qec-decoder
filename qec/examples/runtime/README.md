# General runtime physical-circuit examples

These are detector-annotated Stim circuits, not restricted logical-template JSON.
Both contain H/S/CX compositions and two observable bits, with different physical
qubit counts:

| Circuit | Qubits | Detectors | Edges | Observables |
|---|---:|---:|---:|---:|
| [phase_bell.stim](phase_bell.stim) | 2 | 2 | 2 | 2 |
| [two_repetition_echo.stim](two_repetition_echo.stim) | 6 | 4 | 6 | 2 |

Their source walkthroughs explain the actual experiments:
[phase-Bell verification](phase_bell.md) and
[two repetition-readout echoes](two_repetition_echo.md). Neither demonstrates
arbitrary logical-to-fault-tolerant-QEC synthesis or board acceptance.

From repository root, print a JSON-safe compiled bundle:

```sh
qec/.venv/bin/python -c 'import json; from pathlib import Path; from qec.surface.runtime_circuit import compile_circuit; print(json.dumps(compile_circuit(Path("qec/examples/runtime/phase_bell.stim").read_text()), indent=2))'
```

To compile a zero-noise experiment, explicitly supply the same experiment's noisy
reference instead of asking the compiler to invent noise:

```python
import stim
from pathlib import Path
from qec.surface.runtime_circuit import compile_circuit

noisy = Path('qec/examples/runtime/phase_bell.stim').read_text()
ideal = str(stim.Circuit(noisy).without_noise())
bundle = compile_circuit(ideal, reference_text=noisy)
assert bundle['edges'] == [[0, 1, 3], [0, 2, 1]]
```

`qec/tests/test_runtime_circuit.py` compiles both files and performs real noiseless
and noisy Stim sampling plus PyMatching decoding. Their physical counts do not
fix the runtime decoder's detector capacity. Coordinates and TICK operations are
input-derived; no memory lattice is invented for unrelated circuits.

# Two repetition-readout Clifford echoes

`two_repetition_echo.stim` uses six physical qubits in two independent rows.
Each row executes H, S and a CX chain, then its exact inverse. This general
Clifford composition returns the prepared computational state before noise;
it is not an automatically synthesized fault-tolerant logical operation.

Independent X faults are placed after the echo and before six Z measurements.
Each row's two adjacent parity checks are the detectors. Its first measurement
is the declared observable, giving two independently meaningful observable bits.
The result has four detectors, six edges and boundary index 4:

```text
[0,1,0] [0,4,1] [1,4,0] [2,3,0] [2,4,2] [3,4,0]
```

A single fault is distinguishable within each repetition row; multiple faults
can cause logical prediction failures. This readout model does not include noisy
syndrome-extraction ancillas, a threshold claim or a physical correction loop.
Qubit/check coordinates and two TICK separators support structural timeline
rendering. [Shared usage](README.md) compiles the physical annotated text directly.

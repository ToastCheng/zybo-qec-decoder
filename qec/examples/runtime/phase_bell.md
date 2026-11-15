# Phase-Bell verification

`phase_bell.stim` uses two physical qubits. Reset, H, S and CX prepare
`(|00> + i|11>)/sqrt(2)`. Commuting `Y0*X1` and `Z0*Z1` measurements have
deterministic positive parity in the ideal circuit. Each measurement is both a
detector and a separately declared observable, so this is stabilizer verification,
not a distance-protected logical memory claim.

`X_ERROR(0.02) 0` flips both parities; `Z_ERROR(0.03) 0` flips only the first.
The runtime edges are `[0,1,3]` and `[0,2,1]`, with boundary index 2. This makes
multibit observable preservation directly visible. Coordinates place the two
qubits side by side and detectors at the measurement layer.

[Usage and software verification](README.md) are shared with the second example.

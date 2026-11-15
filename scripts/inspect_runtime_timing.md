# Read-only routed checkpoint diagnostics

`inspect_runtime_timing.tcl CHECKPOINT NEW_PREFIX` opens an existing Vivado DCP
without modifying it and reports 50 setup paths to distinct endpoints, 20 hold
paths, clocks and effective exceptions. Existing report outputs are rejected.
Use the Vivado 2025.2 executable with `-mode batch -source` and `-tclargs`.

The original routed checkpoint is at
`build/runtime-image/vivado_runtime_soc/runtime_soc.runs/impl_1/top_runtime_soc_routed.dcp`.
Diagnostics are archived separately under `build/runtime-image-original-analysis_*`.
Its 50 worst setup paths all end in core parity registers after graph and label
RAM reads. That checkpoint precedes final post-route physical optimization, so
its worst slack (-3.544 ns) differs from the original final summary (-3.479 ns).
Neither report is overwritten. The script adds no false paths, multicycles,
clock changes or DRC waivers and does not generate a bitstream.

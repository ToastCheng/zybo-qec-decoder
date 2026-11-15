# `qec_readback.tcl`

[Source](qec_readback.tcl). Read-only Vivado hardware-manager status query after a separately authorized programming step.

```sh
vivado -mode batch -source scripts/qec_readback.tcl
```

It opens the hardware manager, connects to `localhost:3121`, opens a target, selects the existing `xc7z010_1` device, refreshes it, prints the target name and reports device properties. It then closes the manager. The device name is fixed in this helper; discover the actual JTAG chain first if that name is unavailable or multiple targets are attached.

Inspect configuration properties such as DONE, INIT_B and CRC status in the report. This reads status registers, not the entire programmed bitstream. It does not verify serial request/reply framing, graph identity or decoder correctness. It neither programs the FPGA nor writes boot flash. Hardware access still requires a connected board and working cable permissions.

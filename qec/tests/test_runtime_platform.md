# Runtime platform and builder verification

`test_runtime_platform.py` compiles the maintained production `main.c` with the
real `runtime_platform.h` and native BSP doubles. It does not replace the parser
or GPIO adapter. All native builds use C11, strict warnings, ASan and UBSan;
`-fno-pie -no-pie` avoids native sanitizer placement instability.

## Executed platform checks

The BSP declarations match Vitis 2025.2 SDT base-address lookup, UART FIFO calls,
MMIO and xiltimer. `COUNTS_PER_SECOND` deliberately expands to the unparenthesized
CPU-frequency division used by the generated BSP, catching conversion precedence
and drift bugs rather than hiding them behind a friendly fake constant.

- Lookup, configuration and baud failures terminate silently; no binary UART banner.
- UART1 initialization at 115200, normal operation, nonblocking byte reads including
  0 and 255, and exact output bytes drained through FIFO and transmitter completion.
- GPIO directions at +4/+12 are output/input, without writing control DATA during
  initialization; control at +0 and status at +8 use the fixed runtime address.
- Millisecond scaling near fractional boundaries, large uptime and uint32 wrap.
- An unacknowledged decode times out; a following abort cannot overwrite its toggle.
  After the outstanding ACK settles, metadata reads can proceed.
- The actual infinite production main loop consumes an identity request; the test
  ends it with a native longjmp only after input is exhausted. It validates all
  15 metadata fields, response CRC, exact control-write count and UART draining.

## Builder integration

A missing platform header must fail preflight before importing the vendor module.
The orchestration fixture fakes vendor exports only, then runs real CMake and the
native compiler on the imported maintained source. This catches escaped-quote
errors in `RUNTIME_PLATFORM_HEADER`, stale template sources and source mutation.
The deliberately labeled fake `.elf` is not executable or hardware evidence.

```sh
PYTHONPATH=qec qec/.venv/bin/python -m pytest \
  qec/tests/test_runtime_host.py qec/tests/test_runtime_platform.py \
  qec/tests/test_runtime_build.py -q
```

The separate real Vitis build described in [build_app.md](../../vitis/runtime/build_app.md)
links against the generated Xilinx BSP. Neither native tests nor ARM ELF linkage
prove PL timing or physical operation. No test programs hardware.

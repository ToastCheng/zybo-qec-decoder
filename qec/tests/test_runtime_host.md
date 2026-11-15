# Runtime host and native firmware verification

`test_runtime_host.py` uses real POSIX PTY master/slave streams with pyserial,
not an in-memory Serial mock. `pty_device` validates outgoing request CRC and
fragments responses into three-byte writes. Handler-thread exceptions are
propagated and all ports/threads are closed. `MailboxTestDevice` is a labeled
software serial device with distinctive constant outputs, not FPGA evidence.
`CoreAlgorithmTestDevice` uses the existing half-edge UF core algorithm only
inside a labeled test device; production `runtime_host.py` has no such import or
fallback.

Coverage includes:

- IEEE CRC known vector and exact D4 framing.
- Identity capacities/generation, exact ordered uploads split as 510/510/10 payload
  bytes, and 32-bit predictions.
- Detector widths 1, 9, 17 and 128 over PTYs, inactive-bit rejection and abort/reuse.
- Full local graph validation before BEGIN, device capacity rejection, failed
  COMMIT disarming an older graph, and all dimension/config-valid/generation
  readback mismatches leaving decode disabled.
- Wrong CRC/sequence/magic, oversized reply, status errors and partial response
  timeout; raw bytes remain attached to errors and malformed/incomplete streams
  block all later requests until safely settled. Complete device status replies
  permit another identity request.
- Delayed complete identity and decode replies over real PTYs: a failed bounded
  resynchronization sends nothing, then consuming the old sequence permits reload
  and a fresh decode without one-response lag. Late bytes are archived separately.
- Zero-cycle results and post-shot changes to dimensions, validity and both
  generation halves fail closed; no second shot is sent.
- No retry of an uncertain completed decode; abort/upload remain blocked while
  its reply is unsettled.
- Exclusive port ownership, sequence wrap, nonempty command-ack rejection and
  non-overwriting JSON captures with exact ordered edges/raw frames.
- Actual C parser harness compiled with ASan/UBSan and executed.
- Actual production firmware `main` compiled against a generated native platform
  header, then executed through GPIO metadata reads and a validated identity reply.

Run from repository root:

```sh
PYTHONPATH=qec qec/.venv/bin/python -m pytest qec/tests/test_runtime_host.py -q
```

The C compiler invocation is `cc -std=c11 -Wall -Wextra -Werror -g
-fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie`.
Temporary compiler outputs and platform headers use pytest's scratch directories.
No test opens physical hardware, invokes Vitis, synthesizes RTL or programs a board.
Read the [host interface](../surface/runtime_host.md) and
[firmware contract](../../vitis/runtime/src/main.md) for integration requirements.

# Runtime decoder verification

The runtime path accepts detector-annotated physical Clifford circuits and uploads their ordered decoding graphs without rebuilding the FPGA image. It is distinct from the legacy fixed-ROM memory/H images and from logical-to-fault-tolerant circuit synthesis.

## Built image

Actual Vivado/Vitis 2025.2 artifacts are in `build/runtime-image-v2/` on the build machine:

- `runtime_soc.bit` and `runtime_soc.xsa`.
- `vitis_ws/runtime_app/build/runtime_app.elf`, linked against the matching XSA and real ARM BSP/xiltimer.
- `complete-bundle-verification.json`, pairing routed input-source hashes, bitstream/XSA hashes and firmware source/ELF hashes.

The XSA's embedded bitstream was compared byte-for-byte with the exported `.bit`. Imported firmware C/header files matched maintained sources byte-for-byte. The ELF is a 32-bit ARM EABI5 executable. These checks establish artifact pairing, not board execution.

The [archived manifest](../qec/surface/results/runtime-build-20261115-v2/manifest.json) hashes included raw reports, compiler-to-RTL logs and the exact hardware/firmware source snapshot. It explicitly lists the large binary artifacts as external, not included in Git. Original `verification.json` files retain build-machine-relative evidence locators; use the archive manifest for included files.

## Routed feasibility

Capacity is unchanged at 128 detectors, 512 edges and 32 observable bits on `xc7z010clg400-1`, with 100 MHz FCLK:

- Worst setup slack: +0.095 ns; zero failing setup endpoints.
- Worst hold slack: +0.038 ns; zero failing hold endpoints.
- 7,822 slice LUTs, 3,184 slice registers and three RAMB18 primitives.
- Zero routed DRC findings. Four LED outputs remain without output-delay constraints; internal endpoints are constrained.

The timing margin is positive but small. The Digilent PS preset also emits four negative DDR DQS-to-clock skew warnings; they were retained, not downgraded. This is not an independent DDR qualification.

The first unpipelined route failed setup by 3.479 ns. Registered growth/peeling stages removed the graph-RAM → label-RAM → union-selection → parity-write combinational chain. The successful image uses the same capacities and clock: no false-path or multicycle waiver, reduced frequency, or DRC downgrade was used. Original failed evidence remains in `build/runtime-image/` on the build machine.

## Simulation and software boundaries

Actual Vivado runtime benches reload graphs within one elaborated image and compare predictions with `qec.surface.decoder.decode`. Coverage includes 32-bit masks, malformed-load poisoning/recovery, held results, shot abort preserving the graph, full reset invalidation, high unused syndrome bits and independent cycle edges.

The generated core corpus contains 12 graphs and 474 checked shots. A separate compiler-to-core corpus loads five real Stim experiments, with 128 sampled shots per circuit: two-qubit phase-Bell verification, six-qubit repetition echoes, d3 Z/r3 memory, d3 X/r5 memory and d5 Z/r3 memory. Core answers match the Python UF reference. The d3 X/r5 sample had two logical failures against Stim truth; matching the implementation reference is not zero logical error. A separately labeled synthetic long-path diagnostic crosses the 16-bit cycle-report boundary naturally, measuring 287,940 cycles in the pipelined core.

Native C tests compile the actual firmware parser/GPIO adapter under ASan/UBSan. Host tests use real PTY byte streams, including delayed complete replies. Reset during a toggle-zero decode cannot become a successful zero result: firmware requires completion, positive cycles and consistent post-shot graph identity; the host independently checks cycles and identity. An uncertain stream is blocked until explicit bounded resynchronization validates the outstanding response, followed by graph reload. A one-outstanding-command mailbox does not provide preemptive abort of an unacknowledged decode.

Software/browser checks exercise the general editor, an unlisted Clifford composition, observable bit 31, actual sampled Pauli/detector traces, edit invalidation, initial zero-request behavior, local replay and mobile overflow. Software screenshots are labeled Software; no simulated transport result is presented as physical evidence.

## Reproduce the checks

With the repository Python environment active:

```sh
make test
python -m unittest qec.tests.test_runtime_rtl -v
python scripts/verify_runtime_timing.py build/runtime-image-v2/runtime_soc_timing_summary.rpt
```

For browser checks, start a separate Software server and use a second terminal:

```sh
python -m qec.surface.runtime_web --port 18767
# In another terminal; this must be a Software-only URL:
RUNTIME_WEB_URL=http://127.0.0.1:18767 make test
```

## Remaining acceptance

The runtime image has **not been programmed or tested on the physical board**. Acceptance still requires authorized volatile PL/ARM loading, readback/configuration checks, runtime uploads of several different circuit graphs, actual multibit predictions, malformed-traffic recovery and same-shot comparison with Stim truth and the Python reference. It also requires a fresh physical acceptance archive. No flash writes are needed.

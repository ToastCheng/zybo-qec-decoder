# Runtime mailbox cycle-half regression

`tb_runtime_counter.sv` instantiates the real bridge/core with default 128/512/32
capacities and uploads a reverse-ordered 128-edge path. A single detector defect
must grow all the way to boundary 128, then peel back through the ordered forest.
Only one edge carries mask 0x80000005, so the expected multibit result is direct.
No internal signal is forced and no counter is preloaded.

Run `python scripts/run_runtime_rtl.py --bench counter`. The driver writes all
eight syndrome words. Decode must not acknowledge before 65536 clocks; after
completion, reads must return prediction halves 5/32768, decode-error 0 and
generation 1. An independent rising-edge monitor observes the actual core input
acceptance and first result, checks the DUT cycle count against their difference,
and derives both expected cycle halves from that measurement. No expectation is
read from the DUT counter. This remains valid when pipeline latency changes; the
mailbox still must return both halves correctly and delay acknowledgement.

Pipelined marker: `PASS runtime counter mailbox cycles=287940 low16=25796 high16=4`.
Logs are in `build/runtime-test-counter-227860446d26/`. The watchdog and per-command timeout fail
the executable instead of treating a partial simulation as success. This is
behavioral simulation, not a timing or board-latency measurement.

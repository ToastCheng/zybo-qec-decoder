# `check_sim_logs.py`

[Source](check_sim_logs.py). A command-line guard for Vivado xsim logs. `make sim_bridge` uses it because a simulator process exit code alone does not prove that the testbench reached its success condition.

## Inputs and checks

Pass one or more UTF-8 log paths. The script reads each file and requires the literal marker `PASS ` (including its space), rejects `Fatal:` or `FATAL`, and prints `PASS validated <path>` for each accepted log. A missing argument, unreadable file, absent marker or fatal message exits unsuccessfully. It stops at the first failure.

```sh
python scripts/check_sim_logs.py build/qec_ps_bridge.log build/surface_bridge_sim.log
```

The check validates testbench completion, not the truth of arbitrary log contents. Run the actual bridge simulations first; never replace missing logs with fabricated PASS text. [The simulation runner](qec_sim.md) applies equivalent checks directly to captured subprocess output.

# Standalone tool roots and preflight entry points

Companion to [`test_standalone.py`](test_standalone.py).

## Test flow and assertions

Checks both Vitis entry points report their own missing XSA under a stub vitis import and unrelated cwd. A Tcl harness intercepts create_project to check repository root, board-repository environment and default surface top without Vivado. Makefile defaults must exclude tutorial targets. Log-checker cases reject missing PASS and Fatal even with PASS present. Fake executable tools and copied sim/decoder scripts test selected VIVADO_BIN discovery only.

## Test functions and helpers

- `test_firmware_entry_point_reports_its_own_missing_xsa`
- `test_soc_build_accepts_board_repository_and_uses_its_own_root`
- `test_makefile_defaults_to_surface_and_contains_no_tutorial_targets`
- `test_sim_log_checker_rejects_missing_pass_and_hdl_fatal`
- `test_surface_simulation_uses_selected_tool_directory`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Requires tclsh and normal software dependencies. Stub/fake-tool output is not RTL or firmware correctness evidence; no board access occurs.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_standalone.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.

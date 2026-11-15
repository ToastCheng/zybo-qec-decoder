# Strict compiler frontend and auditable logical evidence

Companion to [`test_surface_compile.py`](test_surface_compile.py).

## Test flow and assertions

Nonoptional tests reject invalid typed/ranged options before artifacts, reject --port before reading absent source, check actionable missing-dependency errors under python -S, reject unsupported/duplicate-key programs and check graph projection preserves observable masks or fails. OPTIONAL tests build all memory/H/CX templates in x/z at d3/d5, verify distance and detector parity, hash/ROM round trips, zero/max noise models, CLI rejection and replayable logical correlation masks. CX expects multibit edges and no single-bit ROM. The nested group helper compares the generated stabilizer group rather than a specific generator basis.

## Test functions and helpers

- `test_h_compile_produces_auditable_artifacts_and_real_decoding`
- `test_vetted_templates_both_bases_and_distances`
- `test_cli_compiles_and_rejects_wrong_image_before_opening_serial`
- `test_invalid_compile_options_fail_without_artifacts`
- `test_zero_and_maximum_noise_models_are_real_and_decodable`
- `test_artifact_records_gate_correlations_and_replayable_decode_evidence`
- `test_port_is_rejected_without_dependencies_or_even_reading_source`
- `test_missing_optional_dependencies_have_actionable_cli_error`
- `test_cli_rejects_unvetted_programs_without_artifacts`
- `test_loss_checked_graph_preserves_all_masks_and_rejects_projection_loss`
- `test_strict_frontend_accepts_only_vetted_templates`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

Optional builds skip when tqec is unavailable; install the pinned qec/requirements-compiler.txt in Python 3.12 to exercise them. All compiler outputs use tmp_path; no board is accessed.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_surface_compile.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.

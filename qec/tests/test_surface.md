# Algorithmic graph, ROM and wire contracts

Companion to [`test_surface.py`](test_surface.py).

## Test flow and assertions

module() dynamically loads the surface decoder without confusing it with the repetition decoder. Tests require graph-size rather than exponential storage, bounded ordered endpoints, ROM round trips for d3/d5 and x/z parity cancellation. A small chain explicitly checks an observable-labelled boundary and disconnected error. Physical-host tests construct exact C3/3C bytes, reject wrong width/checksum/sequence and require explicit --port before serial access.

## Test functions and helpers

- `module`
- `test_surface_graph_is_not_an_exponential_syndrome_lut`
- `test_graph_export_is_roundtrippable_and_scales`
- `test_surface_framing_rejects_old_width_and_bad_responses`
- `test_surface_host_requires_explicit_physical_target`
- `test_union_find_peeling_cancels_syndrome_and_tracks_observable`

pytest supplies requested fixtures (`tmp_path`, `monkeypatch`, `capsys`) and expands declared parameter combinations. Assertions are the output contract: a passing file produces no application result artifact outside paths explicitly exercised by its subprocesses. A failed assertion or unhandled exception fails the corresponding case.

## Dependencies and evidence limits

numpy, Stim/PyMatching; subprocess only exercises argument rejection, never a board.

## Run

From the repository root, in the installed QEC Python environment:

```sh
qec/.venv/bin/python -m pytest -q qec/tests/test_surface.py
```

To select a single function, append `::test_function_name` to the path above. For the complete host regression use `qec/.venv/bin/python -m pytest -q qec/tests`. Tests that explicitly opt into RTL or optional compiler dependencies may skip in the normal host environment.

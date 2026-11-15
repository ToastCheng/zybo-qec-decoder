# `test_source_docs.py`

[Source](test_source_docs.py). Regression check for this repository's adjacent-source-documentation rule.

```sh
python -m pytest scripts/test_source_docs.py -q
```

`maintained_sources()` reads Git's tracked and nonignored untracked file inventory, deduplicates it and selects SystemVerilog, C, Python, Tcl, XDC, JavaScript, CJS, HTML, CSS and the root Makefile. It excludes `results` archives and `fixtures` snapshots, which are preserved historical evidence rather than maintained implementations.

`test_every_source_has_adjacent_documentation()` maps each source path to the same basename with `.md`, checks that it exists and contains at least 200 characters, and reports every missing pair in one assertion. For example, `rtl/common/qec_decoder.sv` requires `rtl/common/qec_decoder.md`.

The size guard catches absent or placeholder docs; it does not prove explanations are correct. Review walkthroughs against source whenever behavior changes. The test includes itself, so it also requires this file. Ignored build outputs and virtual environments never enter the Git inventory.

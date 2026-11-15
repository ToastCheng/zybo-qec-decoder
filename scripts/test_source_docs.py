"""Check that every maintained source has a nonempty adjacent walkthrough.

Run from any directory with ``python -m pytest scripts/test_source_docs.py -q``.
The Git inventory includes new source files but excludes ignored build products;
historical captures and fixture snapshots are not maintained implementations.
"""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SUFFIXES = {".sv", ".c", ".py", ".tcl", ".xdc", ".js", ".cjs", ".html", ".css"}


def maintained_sources():
    """Enumerate the working tree, without mistaking archives for live code."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    for name in sorted(set(output.decode().split("\0")) - {""}):
        path = Path(name)
        if "results" in path.parts or "fixtures" in path.parts:
            continue
        if path.suffix in SOURCE_SUFFIXES or name == "Makefile":
            yield path


def test_every_source_has_adjacent_documentation():
    """A missing walkthrough should fail when a new implementation is added."""
    missing = []
    for source in maintained_sources():
        companion = source.with_suffix(".md")
        path = ROOT / companion
        if not path.is_file() or len(path.read_text().strip()) < 200:
            missing.append(f"{source} -> {companion}")
    assert not missing, "Missing source walkthroughs:\n" + "\n".join(missing)

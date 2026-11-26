"""Repository layout tests guarding directory organization, naming rules, and documentation links."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fpga_sources_are_in_one_tree():
    """RTL, constraints, Vitis firmware, and the Tcl build script all live under `fpga/`."""
    for name in ("rtl", "constraints", "vitis"):
        assert not (ROOT / name).exists(), name
        assert (ROOT / "fpga" / name).is_dir(), name
    assert not list((ROOT / "scripts").rglob("*.tcl"))
    assert (ROOT / "fpga/scripts/build.tcl").is_file()


def test_current_sources_have_no_runtime_prefix():
    """Maintained source trees contain no retired `runtime_` or `test_runtime` filenames."""
    paths = []
    for directory in ["qec/surface", "qec/tests", "fpga", "scripts"]:
        for path in (ROOT / directory).rglob("*"):
            if "results" in path.parts or "__pycache__" in path.parts:
                continue
            if path.is_file() and (
                "runtime_" in path.name or "test_runtime" in path.name
            ):
                paths.append(str(path.relative_to(ROOT)))
    assert paths == [], paths


def test_web_is_the_only_http_interface():
    """Only `qec/surface/web.py` defines HTTP server classes, and the old runtime assets folder is absent."""
    web = ROOT / "qec/surface/web.py"
    assert web.is_file()
    others = []
    for path in (ROOT / "qec/surface").glob("*.py"):
        if path == web:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [ast.unparse(base) for base in node.bases]
            if any(
                "BaseHTTPRequestHandler" in base or "HTTPServer" in base
                for base in bases
            ):
                others.append(path.name)
    assert others == [], others
    assert not (ROOT / "qec/surface/runtime_web_assets").exists()


def test_readme_links_to_the_separate_quickstart():
    """README.md links to `docs/quickstart.md`, includes a diagram, and has no legacy quickstart left over."""
    text = (ROOT / "README.md").read_text()
    assert "docs/quickstart.md" in text
    assert (ROOT / "docs/quickstart.md").is_file()
    assert "```mermaid" in text or ".svg)" in text
    assert not (ROOT / "docs/legacy-memory-quickstart.md").exists()

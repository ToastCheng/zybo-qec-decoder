"""Verify repository documentation links and the code walkthrough coverage.

Checks that `docs/code-walkthrough.md` exists, is linked from `README.md`, and
mentions the main source trees, and verifies that all local relative links in
maintained Markdown files resolve on disk.

Usage:
    pytest scripts/test_source_docs.py
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
GUIDE = Path("docs/code-walkthrough.md")


def maintained_documents():
    """Yield repo-relative paths for tracked and untracked Markdown files, skipping results and fixtures."""
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    for name in sorted(set(output.decode().split("\0")) - {""}):
        path = Path(name)
        if "results" in path.parts or "fixtures" in path.parts:
            continue
        if path.suffix == ".md" and (ROOT / path).is_file():
            yield path


def local_link_paths(text):
    """Extract local file paths from Markdown links and images, ignoring URLs and bare fragments."""
    for destination in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        destination = destination.split()[0].strip("<>")
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        yield unquote(parsed.path)


def test_central_walkthrough_is_linked_and_covers_source_directories():
    """Verify that README links to the code walkthrough and that the walkthrough lists all main source trees."""
    guide = ROOT / GUIDE
    assert guide.is_file(), f"Missing source guide: {GUIDE}"
    text = guide.read_text()
    for directory in (
        "qec/",
        "fpga/rtl/",
        "fpga/scripts/",
        "fpga/vitis/",
        "fpga/constraints/",
    ):
        assert directory in text, f"Source guide omits {directory}"
    assert GUIDE.as_posix() in (ROOT / "README.md").read_text()


def test_maintained_markdown_local_links_resolve():
    """Verify that every local relative link in maintained Markdown docs points to an existing file."""
    missing = []
    for document in maintained_documents():
        for target in local_link_paths((ROOT / document).read_text()):
            if not (ROOT / document.parent / target).exists():
                missing.append(f"{document} -> {target}")
    assert not missing, "Broken local Markdown links:\n" + "\n".join(missing)


def test_local_link_paths_excludes_urls_and_preserves_relative_paths():
    """Verify that link extraction drops external URLs and fragments while unquoting relative paths."""
    text = (
        "[source](../qec/surface/decoder.py#decode) [section](#fpga) "
        "[web](https://example.com/doc) ![image](images/example.png) "
        "[space](file%20name.md)"
    )
    assert list(local_link_paths(text)) == [
        "../qec/surface/decoder.py",
        "images/example.png",
        "file name.md",
    ]

"""Check the central source guide and local links in maintained Markdown.

Run with ``python -m pytest scripts/test_source_docs.py -q``. Historical results
and fixture snapshots retain their original documentation and are excluded.
"""

from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
GUIDE = Path("docs/code-walkthrough.md")


def maintained_documents():
    """Include tracked and new docs, excluding deleted files and archives."""
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
    """Extract inline Markdown paths without interpreting URL fragments as files."""
    for destination in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        destination = destination.split()[0].strip("<>")
        parsed = urlsplit(destination)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        yield unquote(parsed.path)


def test_central_walkthrough_is_linked_and_covers_source_directories():
    guide = ROOT / GUIDE
    assert guide.is_file(), f"Missing source guide: {GUIDE}"
    text = guide.read_text()
    for directory in ("qec/", "rtl/", "scripts/", "vitis/", "constraints/"):
        assert directory in text, f"Source guide omits {directory}"
    assert GUIDE.as_posix() in (ROOT / "README.md").read_text()


def test_maintained_markdown_local_links_resolve():
    missing = []
    for document in maintained_documents():
        for target in local_link_paths((ROOT / document).read_text()):
            if not (ROOT / document.parent / target).exists():
                missing.append(f"{document} -> {target}")
    assert not missing, "Broken local Markdown links:\n" + "\n".join(missing)


def test_local_link_paths_excludes_urls_and_preserves_relative_paths():
    text = (
        "[source](../qec/decoder.py#decode) [section](#rtl) "
        "[web](https://example.com/doc) ![image](images/example.png) "
        "[space](file%20name.md)"
    )
    assert list(local_link_paths(text)) == [
        "../qec/decoder.py", "images/example.png", "file name.md"
    ]

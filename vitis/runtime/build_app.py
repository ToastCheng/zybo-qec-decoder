"""Build standalone runtime firmware with Vitis Unified 2025.2.

Run `vitis -s /path/to/vitis/runtime/build_app.py`. QEC_RUNTIME_OUTPUT_DIR
selects the image directory (default build/runtime-image, repository-relative).
Never reads fixed-image graph settings or changes the maintained firmware.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    image = (
        ROOT / os.environ.get("QEC_RUNTIME_OUTPUT_DIR", "build/runtime-image")
    ).resolve()
    workspace = image / "vitis_ws"
    xsa = image / "runtime_soc.xsa"
    source = ROOT / "vitis/runtime/src"
    if image == ROOT or image in ROOT.parents or image == ROOT / "build":
        raise RuntimeError(
            "Select an isolated runtime image directory, not the repository/build root"
        )
    if image.is_relative_to(ROOT) and not image.is_relative_to(ROOT / "build"):
        raise RuntimeError("Runtime images inside the repository must be under build/")
    if not xsa.is_file():
        raise RuntimeError(f"{xsa} not found; run scripts/build_runtime.tcl first")
    for name in ("main.c", "runtime_platform.h"):
        if not (source / name).is_file():
            raise RuntimeError(f"Runtime firmware missing: {source / name}")
    # Do not delete components or reuse stale exports as evidence of success.
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise RuntimeError(
            f"Refusing nonempty workspace: {workspace}; select a fresh image directory"
        )

    import vitis

    client = vitis.create_client()
    client.set_workspace(path=str(workspace))
    platform = client.create_platform_component(
        name="runtime_platform",
        hw_design=str(xsa),
        os="standalone",
        cpu="ps7_cortexa9_0",
    )
    platform.build()
    platforms = sorted(
        (workspace / "runtime_platform/export/runtime_platform").glob("*.xpfm")
    )
    if len(platforms) != 1:
        raise RuntimeError(
            f"Expected one runtime platform export; found {len(platforms)}"
        )

    app = client.create_app_component(
        name="runtime_app",
        platform=str(platforms[0]),
        domain="standalone_ps7_cortexa9_0",
        template="hello_world",
    )
    app.remove_files(files=["src/helloworld.c"])
    app.import_files(from_loc=str(source), dest_dir_in_cmp="src")
    # Unified Vitis can retain the removed template in USER_COMPILE_SOURCES.
    # Edit only the generated copy; runtime main.c remains the source of truth.
    config = workspace / "runtime_app/src/UserConfig.cmake"
    text = config.read_text()
    text = text.replace('"helloworld.c"\n', "")
    # Preserve the literal C string quotes through CMake and the compiler.
    # Directory compile definitions also apply when the vendor regenerates its
    # source list; no changes to the maintained/imported main.c are necessary.
    text += '\nadd_compile_definitions("RUNTIME_PLATFORM_HEADER=\\"runtime_platform.h\\"")\n'
    config.write_text(text)
    app.build()
    elfs = sorted((workspace / "runtime_app/build").glob("*.elf"))
    if len(elfs) != 1:
        raise RuntimeError(f"Expected one runtime ELF; found {len(elfs)}")
    print(f"Build complete: {elfs[0]}")


if __name__ == "__main__":
    main()

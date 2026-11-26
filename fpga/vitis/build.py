"""Build the standalone ARM Cortex-A9 firmware ELF in a fresh Vitis workspace.

Run via `vitis -s fpga/vitis/build.py`. Reads `qec_soc.xsa` from `QEC_IMAGE_DIR`
(default `build/image`), creates `vitis_ws/` beside it, builds the standalone
BSP (`qec_platform`), compiles `fpga/vitis/src/{main.c,platform.h}` into
`qec_app`, and prints the output `.elf` path.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    """Validate inputs and run the headless Vitis platform + application build."""
    image = (ROOT / os.environ.get("QEC_IMAGE_DIR", "build/image")).resolve()
    workspace = image / "vitis_ws"
    xsa = image / "qec_soc.xsa"
    source = ROOT / "fpga/vitis/src"
    # Keep build outputs isolated under build/<subdir> or outside the repo.
    if image == ROOT or image in ROOT.parents or image == ROOT / "build":
        raise RuntimeError(
            "Select an isolated decoder image directory, not the repository/build root"
        )
    if image.is_relative_to(ROOT) and not image.is_relative_to(ROOT / "build"):
        raise RuntimeError("Decoder images inside the repository must be under build/")
    if not xsa.is_file():
        raise RuntimeError(f"{xsa} not found; run fpga/scripts/build.tcl first")
    for name in ("main.c", "platform.h"):
        if not (source / name).is_file():
            raise RuntimeError(f"Decoder firmware missing: {source / name}")
    # Refuse nonempty workspaces so stale exports cannot pass for a fresh build.
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise RuntimeError(
            f"Refusing nonempty workspace: {workspace}; select a fresh image directory"
        )

    import vitis

    # Create and build the standalone platform BSP for Cortex-A9 core 0.
    client = vitis.create_client()
    client.set_workspace(path=str(workspace))
    platform = client.create_platform_component(
        name="qec_platform",
        hw_design=str(xsa),
        os="standalone",
        cpu="ps7_cortexa9_0",
    )
    platform.build()
    platforms = sorted((workspace / "qec_platform/export/qec_platform").glob("*.xpfm"))
    if len(platforms) != 1:
        raise RuntimeError(f"Expected one platform export; found {len(platforms)}")

    # Seed the application from hello_world, swap in main.c/platform.h, and
    # inject QEC_PLATFORM_HEADER="platform.h" into UserConfig.cmake.
    app = client.create_app_component(
        name="qec_app",
        platform=str(platforms[0]),
        domain="standalone_ps7_cortexa9_0",
        template="hello_world",
    )
    app.remove_files(files=["src/helloworld.c"])
    app.import_files(from_loc=str(source), dest_dir_in_cmp="src")
    # Strip the template entry from Vitis's generated CMake source list as well.
    config = workspace / "qec_app/src/UserConfig.cmake"
    text = config.read_text()
    text = text.replace('"helloworld.c"\n', "")
    # Double-escape quotes so CMake passes a quoted header token to gcc.
    text += '\nadd_compile_definitions("QEC_PLATFORM_HEADER=\\"platform.h\\"")\n'
    config.write_text(text)
    app.build()
    elfs = sorted((workspace / "qec_app/build").glob("*.elf"))
    if len(elfs) != 1:
        raise RuntimeError(f"Expected one QEC ELF; found {len(elfs)}")
    print(f"Build complete: {elfs[0]}")


if __name__ == "__main__":
    main()

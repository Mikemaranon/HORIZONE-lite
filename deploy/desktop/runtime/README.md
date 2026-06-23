# Embedded HORIZONE runtime

This directory contains the native `llama-server` binaries shipped with the
HORIZONE desktop application. They are build inputs, not generated Tauri or
PyInstaller outputs.

The build selects the directory matching the host platform and architecture,
then copies the executable into `deploy/desktop/dist/runtime`. A configured
`HORIZONE_LLAMA_CPP_BINARY` may still override the embedded runtime for local
testing.

The macOS ARM64 binary is self-contained, links Apple Metal directly, and is
ad-hoc signed so it can be embedded and signed with the final application.

## macOS ARM64 provenance

- Project: `ggml-org/llama.cpp`
- Release: `b8920`
- Commit: `15fa3c493bfcd040b5f4dcb29e1c998a0846de16`
- License: MIT; see `LICENSE.llama.cpp`
- Build: static ARM64 executable with Accelerate and embedded Metal shaders

Run `./build_macos_arm64.sh` from this directory to rebuild the checked-in
binary directly from the pinned upstream source. This maintenance command
requires Git, CMake, Xcode Command Line Tools, and network access; building or
running HORIZONE itself does not.

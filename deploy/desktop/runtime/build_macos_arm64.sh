#!/usr/bin/env bash

set -euo pipefail

LLAMA_CPP_TAG="b8920"
LLAMA_CPP_COMMIT="15fa3c493bfcd040b5f4dcb29e1c998a0846de16"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/horizone-llama.cpp.XXXXXX")"
BUILD_DIR="${SOURCE_DIR}/build-horizone"
DESTINATION="${SCRIPT_DIR}/macos-arm64/llama-server"

cleanup() {
    rm -rf "${SOURCE_DIR}"
}
trap cleanup EXIT

git clone --depth 1 --branch "${LLAMA_CPP_TAG}" \
    https://github.com/ggml-org/llama.cpp.git "${SOURCE_DIR}"

ACTUAL_COMMIT="$(git -C "${SOURCE_DIR}" rev-parse HEAD)"
if [[ "${ACTUAL_COMMIT}" != "${LLAMA_CPP_COMMIT}" ]]; then
    echo "Unexpected llama.cpp commit: ${ACTUAL_COMMIT}" >&2
    exit 1
fi

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
    -DBUILD_SHARED_LIBS=OFF \
    -DGGML_NATIVE=OFF \
    -DGGML_METAL=ON \
    -DGGML_METAL_EMBED_LIBRARY=ON \
    -DGGML_ACCELERATE=ON \
    -DGGML_OPENMP=OFF \
    -DLLAMA_CURL=OFF \
    -DLLAMA_OPENSSL=OFF \
    -DLLAMA_BUILD_SERVER=ON \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=ON \
    -DLLAMA_BUILD_TOOLS=ON

cmake --build "${BUILD_DIR}" --config Release --target llama-server --parallel
install -m 755 "${BUILD_DIR}/bin/llama-server" "${DESTINATION}"
strip -x "${DESTINATION}"
codesign --force --sign - --timestamp=none "${DESTINATION}"

(
    cd "${SCRIPT_DIR}"
    shasum -a 256 macos-arm64/llama-server > SHA256SUMS
)

echo "Embedded runtime updated: ${DESTINATION}"

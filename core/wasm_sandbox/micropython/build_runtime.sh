#!/usr/bin/env bash
set -euo pipefail

MICROPYTHON_COMMIT="06bcfd5b74c6d275ae0991a19dab8704299e4e05"
EMSCRIPTEN_VERSION="4.0.10"

script_dir=$(cd "$(dirname "$0")" && pwd)
build_root=${COSMOS_WASM_BUILD_ROOT:-"$script_dir/build"}
micropython_dir="$build_root/micropython"
emsdk_dir="$build_root/emsdk"

mkdir -p "$build_root"
if [ ! -d "$micropython_dir/.git" ]; then
	git clone https://github.com/micropython/micropython.git "$micropython_dir"
fi
git -C "$micropython_dir" fetch --depth 1 origin "$MICROPYTHON_COMMIT"
rm -rf "$micropython_dir/ports/cosmos_wasm"
if git -C "$micropython_dir" apply --reverse --check "$script_dir/vm_budget.patch" 2>/dev/null; then
	git -C "$micropython_dir" apply --reverse "$script_dir/vm_budget.patch"
fi
git -C "$micropython_dir" checkout --detach "$MICROPYTHON_COMMIT"

if [ ! -d "$emsdk_dir/.git" ]; then
	git clone --depth 1 https://github.com/emscripten-core/emsdk.git "$emsdk_dir"
fi
if [ ! -x "$emsdk_dir/upstream/emscripten/emcc" ]; then
	"$emsdk_dir/emsdk" install "$EMSCRIPTEN_VERSION"
	"$emsdk_dir/emsdk" activate "$EMSCRIPTEN_VERSION"
fi
# shellcheck disable=SC1091
source "$emsdk_dir/emsdk_env.sh" >/dev/null

git -C "$micropython_dir" apply "$script_dir/vm_budget.patch"
port_dir="$micropython_dir/ports/cosmos_wasm"
cp -R "$script_dir/port" "$port_dir"
make -C "$port_dir" -j2
"$emsdk_dir/upstream/bin/wasm-opt" \
	"$port_dir/build/cosmos_micropython.wasm" \
	--all-features --disable-tail-call \
	--translate-to-exnref --emit-exnref -Oz \
	-o "$script_dir/cosmos_micropython.wasm"

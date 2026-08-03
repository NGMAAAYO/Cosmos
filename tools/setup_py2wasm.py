#!/usr/bin/env python3
"""Prepare the exact py2wasm/Nuitka-WASI compiler used by Cosmos."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from pathlib import Path


UPSTREAM = "https://github.com/wasmerio/py2wasm.git"
COMMIT = "07da21cac92f5e5967c4bb5d39aaabaee1c70b3e"


def run(command, *, cwd=None) -> None:
	print("+", " ".join(map(str, command)))
	subprocess.run([str(item) for item in command], cwd=cwd, check=True)


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("--python", default="python3.11", help="Python 3.11 executable")
	parser.add_argument("--destination", default=".cache/py2wasm")
	args = parser.parse_args()

	workspace = Path(__file__).resolve().parents[1]
	destination = Path(args.destination)
	if not destination.is_absolute():
		destination = workspace.joinpath(destination)
	destination = destination.absolute()

	if not destination.exists():
		destination.parent.mkdir(parents=True, exist_ok=True)
		run(["git", "clone", "--branch", "wasi", "--single-branch", "--no-tags", UPSTREAM, destination])
	elif not destination.joinpath(".git").is_dir():
		raise SystemExit(f"destination exists but is not a git checkout: {destination}")

	run(["git", "checkout", "--detach", COMMIT], cwd=destination)
	patch_dir = workspace.joinpath("tools", "py2wasm", "patches")
	for patch in sorted(patch_dir.glob("*.patch")):
		applied = subprocess.run(
			["git", "apply", "--reverse", "--check", str(patch)],
			cwd=destination, check=False, capture_output=True,
		)
		if applied.returncode == 0:
			continue
		run(["git", "apply", "--check", patch], cwd=destination)
		run(["git", "apply", patch], cwd=destination)

	venv = destination.joinpath(".venv")
	if not venv.exists():
		run([args.python, "-m", "venv", venv])
	venv_python = venv.joinpath("Scripts", "python.exe") if os.name == "nt" else venv.joinpath("bin", "python")
	packages = [
		"ordered-set==4.1.0",
		"requests==2.32.4",
		"tqdm==4.67.1",
		"zstandard==0.23.0",
	]
	if platform.system() == "Linux":
		packages.append("patchelf==0.17.2.4")
	run([venv_python, "-m", "pip", "install", *packages])

	manifest = {
		"commit": COMMIT,
		"python": str(venv_python.absolute()),
		"root": str(destination),
	}
	destination.joinpath("cosmos-toolchain.json").write_text(
		json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
	)
	print("\nToolchain ready. Configure Cosmos with:")
	print(f"COSMOS_PY2WASM_ROOT={destination}")
	print(f"COSMOS_PY2WASM_PYTHON={venv_python.absolute()}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

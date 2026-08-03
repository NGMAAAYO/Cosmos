"""Short-lived Wasmtime AOT worker used by the py2wasm runtime."""

from __future__ import annotations

import argparse
from pathlib import Path

import wasmtime

from ..runtime import SandboxLimits
from .runtime import _configure_engine


def main() -> int:
	parser = argparse.ArgumentParser()
	parser.add_argument("input")
	parser.add_argument("output")
	parser.add_argument("--max-stack", type=int, required=True)
	parser.add_argument("--max-memory", type=int, required=True)
	args = parser.parse_args()
	limits = SandboxLimits(
		max_wasm_stack=args.max_stack,
		max_guest_memory=args.max_memory,
	)
	engine = wasmtime.Engine(_configure_engine(limits, parallel=True))
	module = wasmtime.Module(engine, Path(args.input).read_bytes())
	Path(args.output).write_bytes(module.serialize())
	return 0


if __name__ == "__main__":
	raise SystemExit(main())

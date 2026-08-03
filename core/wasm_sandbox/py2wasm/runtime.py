"""Persistent Wasmtime runtime for py2wasm-compiled player modules."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Sequence

from ..runtime import (
	SandboxLimits,
	SandboxTurnAborted,
	SandboxUnavailableError,
	WasmPlayer,
)
from .compiler import Py2WasmCompiler

try:
	import wasmtime
except ImportError:
	wasmtime = None


STARTUP_FUEL = 1_000_000_000
DEFAULT_MAX_MEMORY = 64 * 1024 * 1024
DEFAULT_MAX_STACK = 2 * 1024 * 1024


def _configure_engine(limits: SandboxLimits, *, parallel: bool):
	config = wasmtime.Config()
	config.consume_fuel = True
	config.parallel_compilation = parallel
	config.cranelift_opt_level = "speed_and_size"
	config.max_wasm_stack = limits.max_wasm_stack
	config.memory_reservation = limits.max_guest_memory
	config.memory_reservation_for_growth = 0
	config.memory_guard_size = 64 * 1024
	config.memory_may_move = True
	config.debug_info = False
	config.wasm_threads = False
	config.wasm_memory64 = False
	config.wasm_multi_memory = False
	config.wasm_gc = False
	config.wasm_relaxed_simd = False
	return config


class Py2WasmRuntime:
	"""Compile each team once and share its Wasmtime module between units."""

	def __init__(
		self,
		limits: Optional[SandboxLimits] = None,
		*,
		seed: int = 0,
		compiler: Optional[Py2WasmCompiler] = None,
	) -> None:
		if wasmtime is None:
			raise SandboxUnavailableError("py2wasm player mode requires wasmtime")
		self.limits = limits or SandboxLimits(
			fuel_per_turn=100_000_000,
			max_guest_memory=DEFAULT_MAX_MEMORY,
			max_wasm_stack=DEFAULT_MAX_STACK,
		)
		self.seed = int(seed)
		self.compiler = compiler or Py2WasmCompiler()
		self.engine = wasmtime.Engine(_configure_engine(self.limits, parallel=False))
		self._cache: Dict[str, Py2WasmTeam] = {}

	def compile_team(self, team_name: str, player_root: str = "src") -> "Py2WasmTeam":
		artifact = self.compiler.compile_team(team_name, player_root)
		cache_key = f"{team_name}:{artifact.digest}"
		if cache_key not in self._cache:
			if len(self._cache) >= self.limits.max_compiled_teams:
				raise ValueError("compiled-team cache limit exceeded")
			module = self._load_module(artifact)
			self._cache[cache_key] = Py2WasmTeam(
				self, team_name, artifact.digest, module,
			)
		return self._cache[cache_key]

	def _load_module(self, artifact):
		# Tiny injected modules used by unit tests do not warrant a worker.  Real
		# py2wasm modules are compiled in a short-lived process so Cranelift's
		# large parallel working set never becomes permanent server RSS.
		if not isinstance(self.compiler, Py2WasmCompiler):
			return wasmtime.Module(self.engine, artifact.binary)
		version = importlib.metadata.version("wasmtime").replace(os.sep, "_")
		architecture = platform.machine().replace(os.sep, "_")
		cache_path = self.compiler.cache_root.joinpath(
			f"{artifact.digest}-{version}-{architecture}-"
			f"s{self.limits.max_wasm_stack}-m{self.limits.max_guest_memory}.cwasm",
		)
		try:
			return wasmtime.Module.deserialize_file(self.engine, str(cache_path))
		except Exception:
			pass

		cache_path.parent.mkdir(parents=True, exist_ok=True)
		with tempfile.TemporaryDirectory(
			prefix="cosmos-wasmtime-", dir=cache_path.parent,
		) as temporary:
			work = Path(temporary)
			wasm_path = work.joinpath("player.wasm")
			serialized_path = work.joinpath("player.cwasm")
			wasm_path.write_bytes(artifact.binary)
			environment = os.environ.copy()
			project_root = str(Path(__file__).resolve().parents[3])
			environment["PYTHONPATH"] = os.pathsep.join(
				[item for item in (project_root, environment.get("PYTHONPATH")) if item]
			)
			result = subprocess.run(
				[
					sys.executable, "-m", "core.wasm_sandbox.py2wasm.precompile",
					str(wasm_path), str(serialized_path),
					"--max-stack", str(self.limits.max_wasm_stack),
					"--max-memory", str(self.limits.max_guest_memory),
				],
				env=environment, check=False, capture_output=True, text=True, timeout=300,
			)
			if result.returncode:
				diagnostic = (result.stderr or result.stdout).strip()
				raise SandboxUnavailableError(
					f"Wasmtime AOT compilation failed: {diagnostic}"
				)
			module = wasmtime.Module.deserialize_file(self.engine, str(serialized_path))
			try:
				os.replace(serialized_path, cache_path)
			except OSError:
				pass
			return module


class Py2WasmTeam:
	def __init__(self, runtime: Py2WasmRuntime, name: str, digest: str, module) -> None:
		self.runtime = runtime
		self.name = name
		self.digest = digest
		self.module = module
		self._template_memory = None

	def create_player(self, entity_id: int, team_tag: str) -> "Py2WasmPlayer":
		material = f"{self.runtime.seed}:{self.name}:{team_tag}:{entity_id}".encode("utf-8")
		seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "little") or 1
		player = Py2WasmPlayer(self, seed, self._template_memory)
		if self._template_memory is None:
			self._template_memory = bytes(player._memory.read(player._store))
		return player


class Py2WasmPlayer(WasmPlayer):
	"""One CPython heap, module graph, Store and RNG per game entity."""

	def __init__(
		self, team: Py2WasmTeam, seed: int, template_memory: Optional[bytes] = None,
	) -> None:
		self.team = team
		self._controller = None
		self._sensed: Sequence = ()
		self._detected: Sequence = ()
		self._host_calls_remaining = 0
		self._host_error = None
		self._rng_state = int(seed) & ((1 << 64) - 1) or 1
		self._initial_rng_state = self._rng_state
		self.aborted_turns = 0
		self.last_fuel_consumed = 0
		self.last_bytecodes_consumed = 0
		self.last_host_calls = 0

		runtime = team.runtime
		self._store = wasmtime.Store(runtime.engine)
		self._store.set_limits(
			memory_size=runtime.limits.max_guest_memory,
			table_elements=65_536,
			instances=1,
			tables=1,
			memories=1,
		)
		self._store.set_fuel(STARTUP_FUEL)
		wasi = wasmtime.WasiConfig()
		wasi.argv = ["cosmos-player"]
		wasi.env = [("PYTHONHASHSEED", "0")]
		self._store.set_wasi(wasi)

		linker = wasmtime.Linker(runtime.engine)
		linker.define_wasi()
		for item in team.module.imports:
			if item.module == "cosmos" and item.name == "call":
				function = wasmtime.Func(self._store, item.type, self._guest_call)
				linker.define(self._store, "cosmos", "call", function)
			elif item.module == "cosmos" and item.name == "call_float":
				function = wasmtime.Func(self._store, item.type, self._guest_call_float)
				linker.define(self._store, "cosmos", "call_float", function)
		self._instance = linker.instantiate(self._store, team.module)
		self._exports = self._instance.exports(self._store)
		self._memory = self._exports["memory"]
		if template_memory is None:
			try:
				self._exports["_start"](self._store)
			except Exception as exc:
				trap_code = getattr(exc, "trap_code", None)
				if trap_code == wasmtime.TrapCode.OUT_OF_FUEL:
					raise SandboxUnavailableError(
						f"py2wasm startup budget exhausted for team {team.name!r}"
					) from None
				raise SandboxUnavailableError(
					f"cannot initialize py2wasm team {team.name!r}: {exc}"
				) from exc
		else:
			missing = len(template_memory) - self._memory.data_len(self._store)
			if missing > 0:
				self._memory.grow(self._store, (missing + 65_535) // 65_536)
			self._memory.write(self._store, template_memory, 0)

	def run(self, controller):
		limits = self.team.runtime.limits
		self._controller = controller
		self._host_calls_remaining = limits.max_host_calls_per_turn
		self._host_error = None
		self._detected = ()
		budget = limits.fuel_per_turn
		try:
			self._sensed = tuple(controller.sense_nearby_entities())
			if len(self._sensed) > limits.max_sensed_entities:
				raise SandboxTurnAborted("sensed-entity limit exceeded")
			self._store.set_fuel(budget)
			status = self._exports["cosmos_turn"](self._store)
			if status != 0:
				reason = self._host_error or f"player exception (status {status})"
				raise SandboxTurnAborted(reason)
		except SandboxTurnAborted:
			self._reset_py2wasm_unit()
			self.aborted_turns += 1
			raise
		except Exception as exc:
			self._reset_py2wasm_unit()
			self.aborted_turns += 1
			trap_code = getattr(exc, "trap_code", None)
			out_of_fuel = trap_code == wasmtime.TrapCode.OUT_OF_FUEL
			reason = "instruction budget exhausted" if out_of_fuel else f"sandbox trap: {exc}"
			raise SandboxTurnAborted(reason, out_of_fuel=out_of_fuel) from None
		finally:
			self.last_host_calls = max(
				0, limits.max_host_calls_per_turn - self._host_calls_remaining,
			)
			try:
				self.last_fuel_consumed = budget - self._store.get_fuel()
			except Exception:
				self.last_fuel_consumed = budget
			self.last_bytecodes_consumed = 0
			self._controller = None
			self._sensed = ()
			self._detected = ()
			self._host_calls_remaining = 0
		return controller

	def _reset_py2wasm_unit(self) -> None:
		# A Wasm fuel trap can interrupt CPython between reference-count updates,
		# so continuing that interpreter is unsafe.  Reset to the team's pristine
		# post-initialization image.  Controller actions are transactional and are
		# discarded by the game, so the timed-out turn remains externally inert.
		self._memory.write(self._store, self.team._template_memory, 0)
		self._rng_state = self._initial_rng_state

	def close(self) -> None:
		store = getattr(self, "_store", None)
		if store is not None:
			store.close()
		self._exports = None
		self._instance = None
		self._memory = None
		self._store = None

"""Capability-safe MicroPython/Wasm runtime for untrusted Cosmos strategies."""

from __future__ import annotations

import ast
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Tuple

from core import Direction, EntityType, MapLocation, Team

from .abi import ERROR_I64, Op
from .compiler import ENTITY_TYPES, SandboxCompileError

try:
	import wasmtime
except ImportError:  # Keep the explicitly selected native Python mode usable.
	wasmtime = None


MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
TEAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
MODULE_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
TYPE_NAMES = tuple(name for name, _ in sorted(ENTITY_TYPES.items(), key=lambda item: item[1]))
RUNTIME_PATH = Path(__file__).with_name("micropython") / "cosmos_micropython.wasm"
GUEST_ROOT = Path(__file__).with_name("guest")
MAX_GUEST_FILES = 96
HARD_FUEL_PER_BYTECODE = 4096
HARD_FUEL_MINIMUM = 100_000_000
ALLOWED_IMPORTS = {
	"__future__",
	"math",
	"heapq",
	"random",
	"dataclasses",
	"types",
	"core",
	"core.api",
	"core.entity",
	"src",
	"src.template",
}
REQUIRED_EXPORTS = {
	"memory",
	"__indirect_function_table",
	"cosmos_input_ptr",
	"cosmos_input_capacity",
	"cosmos_heap_ptr",
	"cosmos_heap_size",
	"cosmos_state_ptr",
	"cosmos_state_size",
	"cosmos_init",
	"cosmos_add_file",
	"cosmos_exec",
	"cosmos_create_player",
	"cosmos_run",
	"cosmos_budget_remaining",
	"cosmos_error_type_ptr",
	"cosmos_error_type_length",
	"cosmos_error_message_ptr",
	"cosmos_error_message_length",
	"emscripten_stack_init",
	"emscripten_stack_get_current",
	"_emscripten_stack_restore",
}
INERT_WASI_IMPORTS = {"fd_close", "fd_write", "fd_seek"}


class SandboxUnavailableError(RuntimeError):
	pass


class SandboxTurnAborted(RuntimeError):
	def __init__(self, reason: str, *, out_of_fuel: bool = False):
		super().__init__(reason)
		self.reason = reason
		self.out_of_fuel = out_of_fuel


@dataclass(frozen=True)
class SandboxLimits:
	# ``fuel_per_turn`` is retained as the public/configuration name for
	# compatibility.  It now counts Python VM bytecodes, not raw Wasm ops.
	fuel_per_turn: int = 5_000_000
	max_host_calls_per_turn: int = 200_000
	max_sensed_entities: int = 16_384
	max_wasm_stack: int = 512 * 1024
	max_source_bytes: int = 512 * 1024
	max_ast_nodes: int = 200_000
	max_ast_depth: int = 120
	max_compiled_teams: int = 16
	max_guest_memory: int = 4 * 1024 * 1024

	def __post_init__(self):
		if self.fuel_per_turn <= 0:
			raise ValueError("fuel_per_turn must be positive")
		if self.max_host_calls_per_turn <= 0 or self.max_sensed_entities <= 0:
			raise ValueError("host-call and sensed-entity limits must be positive")
		if self.max_wasm_stack < 64 * 1024:
			raise ValueError("max_wasm_stack is too small")
		if self.max_source_bytes <= 0 or self.max_ast_nodes <= 0 or self.max_ast_depth <= 0:
			raise ValueError("source limits must be positive")
		if self.max_compiled_teams <= 0:
			raise ValueError("max_compiled_teams must be positive")
		if self.max_guest_memory < 4 * 1024 * 1024:
			raise ValueError("max_guest_memory is too small for the bundled VM")


def _signed_i64(value: int) -> int:
	value &= MASK64
	return value - (1 << 64) if value >= (1 << 63) else value


def _signed_i32(value: int) -> int:
	value &= MASK32
	return value - (1 << 32) if value >= (1 << 31) else value


def _pack_location(location: MapLocation) -> int:
	return _signed_i64(((int(location.x) & MASK32) << 32) | (int(location.y) & MASK32))


def _unpack_location(value: int) -> MapLocation:
	bits = int(value) & MASK64
	return MapLocation(_signed_i32(bits >> 32), _signed_i32(bits))


def _unpack_direction(value: int) -> Direction:
	value = int(value)
	if value < 0 or value > 8:
		raise ValueError("invalid encoded direction")
	return Direction(value // 3 - 1, value % 3 - 1)


def _type_code(entity_type) -> int:
	name = entity_type.name if hasattr(entity_type, "name") else str(entity_type)
	try:
		return ENTITY_TYPES[name]
	except KeyError as exc:
		raise ValueError(f"unknown entity type {name!r}") from exc


def _entity_type(value: int) -> EntityType:
	value = int(value)
	if value < 0 or value >= len(TYPE_NAMES):
		raise ValueError("invalid encoded entity type")
	return EntityType(TYPE_NAMES[value])


def _team_code(team) -> int:
	tag = team.tag if hasattr(team, "tag") else str(team)
	return -1 if tag == "Neutral" else int(tag)


def _team_from_code(value: int) -> Team:
	return Team("Neutral" if int(value) == -1 else str(int(value)))


def _ast_depth(node: ast.AST) -> int:
	maximum = 0
	stack = [(node, 1)]
	while stack:
		current, depth = stack.pop()
		maximum = max(maximum, depth)
		stack.extend((child, depth + 1) for child in ast.iter_child_nodes(current))
	return maximum


def _resolve_import(module_path: str, node: ast.ImportFrom) -> str:
	if not node.level:
		return node.module or ""
	package = module_path.split(".")[:-1]
	remove = node.level - 1
	if remove > len(package):
		return ""
	base = package[:len(package) - remove] if remove else package
	if node.module:
		base.extend(node.module.split("."))
	return ".".join(base)


def _validate_player_source(
	filename: Path,
	module_path: str,
	source: str,
	team_prefix: str,
	limits: SandboxLimits,
) -> int:
	try:
		tree = ast.parse(source, filename=str(filename))
	except SyntaxError as exc:
		raise SandboxCompileError(str(exc)) from exc
	nodes = list(ast.walk(tree))
	if len(nodes) > limits.max_ast_nodes:
		raise SandboxCompileError(f"{filename}: AST exceeds {limits.max_ast_nodes} nodes")
	if _ast_depth(tree) > limits.max_ast_depth:
		raise SandboxCompileError(f"{filename}: AST nesting exceeds {limits.max_ast_depth}")
	for node in nodes:
		modules: Iterable[str]
		if isinstance(node, ast.Import):
			modules = (alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom):
			modules = (_resolve_import(module_path, node),)
		else:
			continue
		for imported in modules:
			if imported in ALLOWED_IMPORTS or imported.startswith(team_prefix + "."):
				continue
			raise SandboxCompileError(
				f"{filename}:{node.lineno}: import {imported!r} is outside the player API whitelist"
			)
	return len(nodes)


class _MicroPythonCompatibility(ast.NodeTransformer):
	"""Lower small CPython-only integer APIs to capability-free helpers."""

	_HELPERS = {
		"bit_length": "__cosmos_int_bit_length",
		"bit_count": "__cosmos_int_bit_count",
	}

	def __init__(self) -> None:
		self.helpers = set()

	def visit_Call(self, node: ast.Call):
		node = self.generic_visit(node)
		if (
			isinstance(node.func, ast.Attribute)
			and node.func.attr in self._HELPERS
			and not node.args
			and not node.keywords
		):
			helper = self._HELPERS[node.func.attr]
			self.helpers.add((node.func.attr, helper))
			return ast.copy_location(
				ast.Call(
					func=ast.Name(id=helper, ctx=ast.Load()),
					args=[node.func.value],
					keywords=[],
				),
				node,
			)
		return node


def _rewrite_micropython_compatibility(source: str, filename: Path) -> bytes:
	"""Keep accepted player source compatible with the bundled MicroPython."""

	tree = ast.parse(source, filename=str(filename))
	transformer = _MicroPythonCompatibility()
	tree = transformer.visit(tree)
	if not transformer.helpers:
		return source.encode("utf-8")

	imports = ast.ImportFrom(
		module="core.api",
		names=[
			ast.alias(name=method, asname=helper)
			for method, helper in sorted(transformer.helpers)
		],
		level=0,
	)
	insert_at = 0
	if (
		tree.body
		and isinstance(tree.body[0], ast.Expr)
		and isinstance(tree.body[0].value, ast.Constant)
		and isinstance(tree.body[0].value.value, str)
	):
		insert_at = 1
	while (
		insert_at < len(tree.body)
		and isinstance(tree.body[insert_at], ast.ImportFrom)
		and tree.body[insert_at].module == "__future__"
	):
		insert_at += 1
	tree.body.insert(insert_at, imports)
	ast.fix_missing_locations(tree)
	return (ast.unparse(tree) + "\n").encode("utf-8")


class _EmscriptenLongjmp(BaseException):
	"""Internal signal used by Emscripten's portable setjmp lowering."""


class WasmRuntime:
	"""Own one Wasmtime engine/module and cache one initialized image per team."""

	def __init__(self, limits: Optional[SandboxLimits] = None, *, seed: int = 0):
		if wasmtime is None:
			raise SandboxUnavailableError(
				"WebAssembly player mode requires wasmtime; install requirements.txt"
			)
		if not RUNTIME_PATH.is_file():
			raise SandboxUnavailableError(
				f"bundled MicroPython runtime is missing; run {RUNTIME_PATH.parent / 'build_runtime.sh'}"
			)
		self.limits = limits or SandboxLimits()
		self.seed = int(seed)
		config = wasmtime.Config()
		config.consume_fuel = True
		config.max_wasm_stack = self.limits.max_wasm_stack
		config.debug_info = False
		config.wasm_threads = False
		config.wasm_memory64 = False
		config.wasm_multi_memory = False
		config.wasm_simd = False
		config.wasm_relaxed_simd = False
		config.wasm_gc = False
		config.wasm_exceptions = True
		config.wasm_tail_call = False
		self.engine = wasmtime.Engine(config)
		try:
			self.module = wasmtime.Module(self.engine, RUNTIME_PATH.read_bytes())
		except Exception as exc:
			raise SandboxUnavailableError(f"cannot load bundled MicroPython runtime: {exc}") from exc
		self._validate_module(self.module)
		self._cache: Dict[str, WasmTeam] = {}

	def compile_team(self, team_name: str, player_root: str = "src") -> "WasmTeam":
		if not TEAM_NAME.fullmatch(team_name):
			raise ValueError(f"invalid team name {team_name!r}")
		root = Path(player_root).resolve()
		team_root = (root / team_name).resolve()
		if root not in team_root.parents or not team_root.is_dir():
			raise ValueError("player team directory is missing or escapes player_root")
		main_path = team_root / "main.py"
		if not main_path.is_file():
			raise ValueError(f"player entrypoint is missing: {main_path}")

		files: Dict[str, bytes] = {}
		total_bytes = 0
		total_nodes = 0
		team_prefix = f"src.{team_name}"
		for source_path in sorted(team_root.rglob("*.py")):
			resolved = source_path.resolve()
			if team_root not in resolved.parents or source_path.is_symlink():
				raise ValueError(f"player source escapes team directory: {source_path}")
			relative = source_path.relative_to(team_root)
			parts = list(relative.with_suffix("").parts)
			if any(not MODULE_PART.fullmatch(part) for part in parts):
				raise ValueError(f"invalid Python module path: {relative}")
			data = source_path.read_bytes()
			total_bytes += len(data)
			if total_bytes > self.limits.max_source_bytes:
				raise ValueError(f"player source exceeds {self.limits.max_source_bytes} bytes")
			try:
				source = data.decode("utf-8")
			except UnicodeDecodeError as exc:
				raise SandboxCompileError(f"{source_path}: source must be UTF-8") from exc
			module_parts = [team_prefix, *parts]
			if parts[-1] == "__init__":
				module_parts.pop()
			module_path = ".".join(module_parts)
			total_nodes += _validate_player_source(
				source_path, module_path, source, team_prefix, self.limits,
			)
			if total_nodes > self.limits.max_ast_nodes:
				raise SandboxCompileError(
					f"{team_root}: combined AST exceeds {self.limits.max_ast_nodes} nodes"
				)
			files[f"src/{team_name}/{relative.as_posix()}"] = (
				_rewrite_micropython_compatibility(source, source_path)
			)

		digest_builder = hashlib.sha256()
		for name, data in sorted(files.items()):
			digest_builder.update(name.encode("utf-8") + b"\0" + data + b"\0")
		digest = digest_builder.hexdigest()
		cache_key = f"{team_root}:{digest}"
		if cache_key not in self._cache:
			if len(self._cache) >= self.limits.max_compiled_teams:
				raise ValueError("compiled-team cache limit exceeded")
			self._cache[cache_key] = WasmTeam(self, team_name, digest, files)
		return self._cache[cache_key]

	@staticmethod
	def _validate_module(module) -> None:
		for item in module.imports:
			allowed = (
				item.module == "cosmos" and item.name in {"call", "call_float"}
			) or (
				item.module == "env"
				and (item.name.startswith("invoke_") or item.name == "_emscripten_throw_longjmp")
			) or (
				item.module == "wasi_snapshot_preview1" and item.name in INERT_WASI_IMPORTS
			)
			if not allowed or not isinstance(item.type, wasmtime.FuncType):
				raise SandboxUnavailableError(
					f"bundled runtime has unexpected import {item.module}.{item.name}"
				)
		exports = {item.name for item in module.exports}
		missing = REQUIRED_EXPORTS - exports
		if missing:
			raise SandboxUnavailableError(
				f"bundled runtime is missing exports: {', '.join(sorted(missing))}"
			)


class _GuestInstance:
	"""Wasmtime/Emscripten plumbing shared by team templates and live units."""

	def _instantiate(self, runtime: WasmRuntime) -> None:
		self._store = wasmtime.Store(runtime.engine)
		self._store.set_limits(
			memory_size=runtime.limits.max_guest_memory,
			table_elements=4096,
			instances=1,
			tables=1,
			memories=1,
		)
		self._store.set_fuel(max(HARD_FUEL_MINIMUM, runtime.limits.fuel_per_turn * HARD_FUEL_PER_BYTECODE))
		imports = []
		for item in runtime.module.imports:
			if item.module == "env" and item.name.startswith("invoke_"):
				imports.append(wasmtime.Func(
					self._store,
					item.type,
					self._invoke(item.name[7] == "v"),
					access_caller=True,
				))
			elif item.module == "env" and item.name == "_emscripten_throw_longjmp":
				imports.append(wasmtime.Func(self._store, item.type, self._throw_longjmp))
			elif item.module == "cosmos" and item.name == "call":
				imports.append(wasmtime.Func(self._store, item.type, self._guest_call))
			elif item.module == "cosmos" and item.name == "call_float":
				imports.append(wasmtime.Func(self._store, item.type, self._guest_call_float))
			elif item.module == "wasi_snapshot_preview1" and item.name in INERT_WASI_IMPORTS:
				imports.append(wasmtime.Func(self._store, item.type, self._inert_wasi))
			else:  # Validated before this point.
				raise SandboxUnavailableError(f"unsupported runtime import {item.module}.{item.name}")
		self._instance = wasmtime.Instance(self._store, runtime.module, imports)
		self._exports = self._instance.exports(self._store)
		self._memory = self._exports["memory"]
		self._exports["emscripten_stack_init"](self._store)

	@staticmethod
	def _throw_longjmp():
		raise _EmscriptenLongjmp()

	@staticmethod
	def _invoke(is_void: bool):
		def invoke(caller, function_index, *args):
			table = caller.get("__indirect_function_table")
			stack_pointer = caller.get("emscripten_stack_get_current")(caller)
			try:
				result = table.get(caller, function_index)(caller, *args)
				return None if is_void else result
			except _EmscriptenLongjmp:
				caller.get("_emscripten_stack_restore")(caller, stack_pointer)
				caller.get("setThrew")(caller, 1, 0)
				return None if is_void else 0
		return invoke

	def _error_type(self) -> str:
		try:
			pointer = self._exports["cosmos_error_type_ptr"](self._store)
			length = self._exports["cosmos_error_type_length"](self._store)
			error_type = bytes(self._memory.read(self._store, pointer, pointer + length)).decode("ascii", "replace")
			message_pointer = self._exports["cosmos_error_message_ptr"](self._store)
			message_length = self._exports["cosmos_error_message_length"](self._store)
			message = bytes(self._memory.read(
				self._store, message_pointer, message_pointer + message_length,
			)).decode("utf-8", "replace")
			return f"{error_type}: {message}" if message else error_type
		except Exception:
			return "guest error"

	def _guest_call(self, opcode, a, b, c):
		return ERROR_I64

	def _guest_call_float(self, opcode, a, b, c):
		return math.nan

	@staticmethod
	def _inert_wasi(*args):
		# These Emscripten libc fallbacks are deliberately capability-free: no
		# preopens, filesystem implementation, clocks, sockets or process API.
		return 8  # WASI_ERRNO_BADF


class WasmTeam(_GuestInstance):
	def __init__(self, runtime: WasmRuntime, name: str, digest: str, player_files: Dict[str, bytes]):
		self.runtime = runtime
		self.name = name
		self.digest = digest
		self.module = runtime.module
		self.wat = None
		self._instantiate(runtime)
		self._exports["cosmos_init"](self._store)

		files = {
			"core/__init__.py": b"",
			"src/__init__.py": b"",
			f"src/{name}/__init__.py": b"",
		}
		for path in sorted(GUEST_ROOT.rglob("*.py")):
			files[path.relative_to(GUEST_ROOT).as_posix()] = path.read_bytes()
		files.update(player_files)
		bootstrap = (
			"import random\n"
			"from core.entity import Controller\n"
			f"from src.{name}.main import Player\n"
			"__cosmos_controller = Controller()\n"
			"__cosmos_player = None\n"
			"def __cosmos_create_player(seed):\n"
			"    global __cosmos_player\n"
			"    random.seed(seed)\n"
			"    __cosmos_player = Player()\n"
			"def __cosmos_turn():\n"
			"    __cosmos_controller._begin_turn()\n"
			"    return __cosmos_player.run(__cosmos_controller)\n"
		).encode("utf-8")

		payload = bytearray()
		registrations = []
		for filename, source in sorted(files.items()):
			name_offset = len(payload)
			encoded_name = filename.encode("utf-8")
			payload.extend(encoded_name)
			source_offset = len(payload)
			payload.extend(source)
			registrations.append((name_offset, len(encoded_name), source_offset, len(source)))
		bootstrap_offset = len(payload)
		payload.extend(bootstrap)
		capacity = self._exports["cosmos_input_capacity"](self._store)
		if len(payload) > capacity or len(registrations) > MAX_GUEST_FILES:
			raise SandboxCompileError("team source exceeds the isolated VM input capacity")
		input_pointer = self._exports["cosmos_input_ptr"](self._store)
		self._memory.write(self._store, payload, input_pointer)
		for registration in registrations:
			if self._exports["cosmos_add_file"](self._store, *registration) != 0:
				raise SandboxCompileError("cannot register a player source file in the isolated VM")
		status = self._exports["cosmos_exec"](self._store, bootstrap_offset, len(bootstrap))
		if status != 0:
			raise SandboxCompileError(
				f"MicroPython rejected team {name!r}: {self._error_type()}"
			)
		self._template_memory = bytes(self._memory.read(self._store))

	def create_player(self, entity_id: int, team_tag: str) -> "WasmPlayer":
		seed_material = f"{self.runtime.seed}:{self.name}:{team_tag}:{entity_id}".encode("utf-8")
		seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "little") or 1
		return WasmPlayer(self, seed)


class WasmPlayer(_GuestInstance):
	"""One isolated Store, linear memory, module graph and RNG per entity."""

	def __init__(self, team: WasmTeam, seed: int):
		self.team = team
		self._controller = None
		self._sensed: Sequence = ()
		self._detected: Sequence = ()
		self._host_calls_remaining = 0
		self._host_error = None
		self._rng_state = int(seed) & MASK64 or 1
		self.aborted_turns = 0
		self.last_fuel_consumed = 0
		self.last_bytecodes_consumed = 0
		self.last_host_calls = 0
		self._instantiate(team.runtime)
		self._memory.write(self._store, team._template_memory, 0)
		status = self._exports["cosmos_create_player"](self._store, _signed_i64(seed))
		if status != 0:
			raise SandboxCompileError(
				f"cannot initialize Player for team {team.name!r}: {self._error_type()}"
			)

	def run(self, controller):
		limits = self.team.runtime.limits
		memory_snapshot = self._snapshot_mutable_state()
		rng_snapshot = self._rng_state
		stack_pointer = self._exports["emscripten_stack_get_current"](self._store)
		budget = limits.fuel_per_turn
		hard_fuel = max(HARD_FUEL_MINIMUM, budget * HARD_FUEL_PER_BYTECODE)
		self._controller = controller
		self._host_calls_remaining = limits.max_host_calls_per_turn
		self._host_error = None
		self._detected = ()
		try:
			self._sensed = tuple(controller.sense_nearby_entities())
			if len(self._sensed) > limits.max_sensed_entities:
				raise SandboxTurnAborted("sensed-entity limit exceeded")
			self._store.set_fuel(hard_fuel)
			status = self._exports["cosmos_run"](self._store, budget)
			if status != 0:
				reason = "instruction budget exhausted" if status == 1 else f"player exception: {self._error_type()}"
				raise SandboxTurnAborted(reason, out_of_fuel=status == 1)
		except SandboxTurnAborted:
			self._restore_turn(memory_snapshot, rng_snapshot, stack_pointer)
			self.aborted_turns += 1
			raise
		except Exception as exc:
			self._restore_turn(memory_snapshot, rng_snapshot, stack_pointer)
			self.aborted_turns += 1
			trap_code = getattr(exc, "trap_code", None)
			out_of_fuel = trap_code == wasmtime.TrapCode.OUT_OF_FUEL
			reason = "hard Wasm instruction budget exhausted" if out_of_fuel else f"sandbox trap: {exc}"
			raise SandboxTurnAborted(reason, out_of_fuel=out_of_fuel) from None
		finally:
			self.last_host_calls = max(
				0, limits.max_host_calls_per_turn - self._host_calls_remaining,
			)
			try:
				self.last_fuel_consumed = hard_fuel - self._store.get_fuel()
			except Exception:
				self.last_fuel_consumed = hard_fuel
			try:
				remaining = self._exports["cosmos_budget_remaining"](self._store)
				self.last_bytecodes_consumed = max(0, min(budget, budget - remaining))
			except Exception:
				self.last_bytecodes_consumed = budget
			self._controller = None
			self._sensed = ()
			self._detected = ()
			self._host_calls_remaining = 0
		return controller

	def _snapshot_mutable_state(self):
		heap_pointer = self._exports["cosmos_heap_ptr"](self._store)
		heap_size = self._exports["cosmos_heap_size"](self._store)
		state_pointer = self._exports["cosmos_state_ptr"](self._store)
		state_size = self._exports["cosmos_state_size"](self._store)
		return (
			(heap_pointer, bytes(self._memory.read(
				self._store, heap_pointer, heap_pointer + heap_size,
			))),
			(state_pointer, bytes(self._memory.read(
				self._store, state_pointer, state_pointer + state_size,
			))),
		)

	def _restore_turn(self, memory_snapshot, rng_snapshot: int, stack_pointer: int) -> None:
		for pointer, data in memory_snapshot:
			self._memory.write(self._store, data, pointer)
		self._exports["_emscripten_stack_restore"](self._store, stack_pointer)
		self._rng_state = rng_snapshot

	def _consume_host_call(self) -> bool:
		if self._host_calls_remaining <= 0:
			self._host_error = "host-call budget exhausted"
			return False
		self._host_calls_remaining -= 1
		return True

	def _guest_call(self, opcode, a, b, c):
		if not self._consume_host_call():
			return ERROR_I64
		try:
			return _signed_i64(self._host_call(Op(opcode), (a, b, c)))
		except Exception as exc:
			self._host_error = f"{type(exc).__name__}: {exc}"
			return ERROR_I64

	def _guest_call_float(self, opcode, a, b, c):
		if not self._consume_host_call():
			return math.nan
		try:
			return float(self._host_call(Op(opcode), (a, b, c)))
		except Exception as exc:
			self._host_error = f"{type(exc).__name__}: {exc}"
			return math.nan

	def _require_controller(self):
		if self._controller is None:
			raise RuntimeError("host API called outside a player turn")
		return self._controller

	def _sense(self, index: int):
		index = int(index)
		if index < 0 or index >= len(self._sensed):
			raise ValueError("sensed entity index is out of range")
		return self._sensed[index]

	def _host_call(self, opcode: Op, args: Tuple[int, int, int]):
		controller = self._require_controller()
		a, b, c = args
		if opcode == Op.GET_ROUND_NUM: return int(controller.get_round_num())
		if opcode == Op.GET_COOLDOWN_TURNS: return int(controller.get_cooldown_turns())
		if opcode == Op.GET_ENERGY: return int(controller.get_energy())
		if opcode == Op.GET_DEFENCE: return int(controller.get_defence())
		if opcode == Op.GET_ID: return int(controller.get_id())
		if opcode == Op.GET_LOCATION: return _pack_location(controller.get_location())
		if opcode == Op.GET_TEAM: return _team_code(controller.get_team())
		if opcode == Op.GET_TYPE: return _type_code(controller.get_type())
		if opcode == Op.GET_RADIO: return int(controller.get_radio())
		if opcode == Op.GET_CHARGE_POINT: return int(controller.get_charge_point())
		if opcode == Op.GET_ENTITY_COUNT: return int(controller.get_entity_count())
		if opcode == Op.IS_READY: return int(controller.is_ready())
		if opcode == Op.GET_ALL_TEAMS_COUNT: return len(controller.get_all_teams())
		if opcode == Op.GET_ALL_TEAMS_AT: return _team_code(controller.get_all_teams()[int(a)])
		if opcode == Op.GET_OPPONENT_COUNT: return len(controller.get_opponent())
		if opcode == Op.GET_OPPONENT_AT: return _team_code(controller.get_opponent()[int(a)])
		if opcode == Op.GET_OVERDRIVE_FACTOR:
			return float(controller.get_overdrive_factor(_team_from_code(a), int(b)))
		if opcode == Op.IS_OPPONENT: return int(controller.is_opponent(_team_from_code(a)))
		if opcode == Op.IS_BLOCKED: return int(controller.is_blocked(_unpack_direction(a)))
		if opcode == Op.IS_LOCATION_OCCUPIED: return int(controller.is_location_occupied(_unpack_location(a)))
		if opcode == Op.ON_THE_MAP: return int(controller.on_the_map(_unpack_location(a)))
		if opcode == Op.CAN_DETECT_LOCATION: return int(controller.can_detect_location(_unpack_location(a)))
		if opcode == Op.CAN_DETECT_RADIUS: return int(controller.can_detect_radius(int(a)))
		if opcode == Op.CAN_SENSE_LOCATION: return int(controller.can_sense_location(_unpack_location(a)))
		if opcode == Op.CAN_SENSE_RADIUS: return int(controller.can_sense_radius(int(a)))
		if opcode == Op.SENSE_AETHER: return float(controller.sense_aether(_unpack_location(a)))
		if opcode == Op.CAN_CHARGE: return int(controller.can_charge(int(a)))
		if opcode == Op.CAN_BUILD: return int(controller.can_build(_entity_type(a), _unpack_direction(b), int(c)))
		if opcode == Op.CAN_OVERDRIVE: return int(controller.can_overdrive(int(a)))
		if opcode == Op.CAN_ANALYZE_ID: return int(controller.can_analyze(int(a)))
		if opcode == Op.CAN_ANALYZE_LOCATION: return int(controller.can_analyze(_unpack_location(a)))
		if opcode == Op.CAN_MOVE: return int(controller.can_move(_unpack_direction(a)))
		if opcode == Op.CAN_SET_RADIO: return int(controller.can_set_radio(int(a)))
		if opcode == Op.CHARGE: controller.charge(int(a)); return 0
		if opcode == Op.BUILD: controller.build(_entity_type(a), _unpack_direction(b), int(c)); return 0
		if opcode == Op.OVERDRIVE: controller.overdrive(int(a)); return 0
		if opcode == Op.ANALYZE_ID: controller.analyze(int(a)); return 0
		if opcode == Op.ANALYZE_LOCATION: controller.analyze(_unpack_location(a)); return 0
		if opcode == Op.MOVE: controller.move(_unpack_direction(a)); return 0
		if opcode == Op.SET_RADIO: controller.set_radio(int(a)); return 0
		if opcode == Op.SENSE_COUNT: return len(self._sensed)
		if opcode == Op.SENSE_ID: return int(self._sense(a).ID)
		if opcode == Op.SENSE_ENERGY: return int(self._sense(a).energy)
		if opcode == Op.SENSE_DEFENCE: return int(self._sense(a).defence)
		if opcode == Op.SENSE_INIT_DEFENCE: return int(self._sense(a).init_defence)
		if opcode == Op.SENSE_LOCATION: return _pack_location(self._sense(a).location)
		if opcode == Op.SENSE_TEAM: return _team_code(self._sense(a).team)
		if opcode == Op.SENSE_TYPE: return _type_code(self._sense(a).type)
		if opcode == Op.SENSE_RADIO: return int(self._sense(a).radio)
		if opcode == Op.DETECT_PREPARE:
			self._detected = tuple(controller.detect_nearby_entities(int(a)))
			return len(self._detected)
		if opcode == Op.DETECT_LOCATION:
			index = int(a)
			if index < 0 or index >= len(self._detected):
				raise ValueError("detected entity index is out of range")
			return _pack_location(self._detected[index])
		if opcode == Op.RANDOM_INT: return self._random_int(a)
		raise RuntimeError(f"unimplemented host opcode {opcode}")

	def _random_int(self, limit: int) -> int:
		limit = int(limit)
		if limit <= 0 or limit >= (1 << 63):
			raise ValueError("random_int limit must be between 1 and 2^63-1")
		x = self._rng_state
		x ^= (x << 13) & MASK64
		x ^= x >> 7
		x ^= (x << 17) & MASK64
		self._rng_state = x & MASK64 or 1
		return self._rng_state % limit

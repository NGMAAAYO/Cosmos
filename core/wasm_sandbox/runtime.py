"""Wasmtime host for restricted Cosmos player strategies."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from core import Direction, EntityType, MapLocation, Team

from .compiler import ENTITY_TYPES, HOST_IMPORTS, HostImport, compile_restricted_python

try:
	import wasmtime
except ImportError:  # Keep the legacy Python runtime usable without the optional dependency.
	wasmtime = None


MASK32 = (1 << 32) - 1
MASK64 = (1 << 64) - 1
TEAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
TYPE_NAMES = tuple(name for name, _ in sorted(ENTITY_TYPES.items(), key=lambda item: item[1]))
TYPE_ACTION_RADIUS = (2, 9, 0, 12)
TYPE_DETECTION_RADIUS = (40, 25, 20, 40)
TYPE_INITIAL_COOLDOWN = (0, 10, 0, 10)
TYPE_SENSOR_RADIUS = (40, 25, 20, 30)
ALL_DIRECTIONS = ((0, 0), (0, -1), (0, 1), (-1, 0), (-1, -1), (-1, 1), (1, 0), (1, -1), (1, 1))
CARDINAL_DIRECTIONS = ((0, 1), (0, -1), (1, 0), (-1, 0))


class SandboxUnavailableError(RuntimeError):
	pass


class SandboxTurnAborted(RuntimeError):
	def __init__(self, reason: str, *, out_of_fuel: bool = False):
		super().__init__(reason)
		self.reason = reason
		self.out_of_fuel = out_of_fuel


@dataclass(frozen=True)
class SandboxLimits:
	fuel_per_turn: int = 100_000
	max_host_calls_per_turn: int = 10_000
	max_sensed_entities: int = 4_096
	max_wasm_stack: int = 512 * 1024
	max_source_bytes: int = 128 * 1024
	max_ast_nodes: int = 20_000
	max_ast_depth: int = 80
	max_compiled_teams: int = 16

	def __post_init__(self):
		if self.fuel_per_turn <= 0:
			raise ValueError("fuel_per_turn must be positive")
		if self.max_host_calls_per_turn <= 0 or self.max_sensed_entities <= 0:
			raise ValueError("host-call and sensed-entity limits must be positive")
		if self.max_wasm_stack < 64 * 1024:
			raise ValueError("max_wasm_stack is too small")
		if self.max_compiled_teams <= 0:
			raise ValueError("max_compiled_teams must be positive")


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


def _pack_direction(direction: Direction) -> int:
	dx, dy = int(direction.dx), int(direction.dy)
	if dx < -1 or dx > 1 or dy < -1 or dy > 1:
		raise ValueError("direction components must be between -1 and 1")
	return (dx + 1) * 3 + (dy + 1)


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


class WasmRuntime:
	"""Owns one Wasmtime engine and compiles each team source once."""

	def __init__(self, limits: Optional[SandboxLimits] = None, *, seed: int = 0):
		if wasmtime is None:
			raise SandboxUnavailableError(
				"WebAssembly player mode requires wasmtime; install requirements.txt"
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
		config.wasm_reference_types = False
		config.wasm_function_references = False
		config.wasm_gc = False
		config.wasm_exceptions = False
		config.wasm_tail_call = False
		self.engine = wasmtime.Engine(config)
		self._cache: Dict[str, WasmTeam] = {}

	def compile_team(self, team_name: str, player_root: str = "src") -> "WasmTeam":
		if not TEAM_NAME.fullmatch(team_name):
			raise ValueError(f"invalid team name {team_name!r}")
		root = Path(player_root).resolve()
		source_path = (root / team_name / "main.py").resolve()
		if root not in source_path.parents:
			raise ValueError("player source escapes player_root")
		with source_path.open("rb") as source_file:
			source_bytes = source_file.read(self.limits.max_source_bytes + 1)
		if len(source_bytes) > self.limits.max_source_bytes:
			raise ValueError(f"player source exceeds {self.limits.max_source_bytes} bytes")
		source = source_bytes.decode("utf-8")
		digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
		cache_key = f"{source_path}:{digest}"
		if cache_key not in self._cache:
			if len(self._cache) >= self.limits.max_compiled_teams:
				raise ValueError("compiled-team cache limit exceeded")
			wat = compile_restricted_python(
				source,
				str(source_path),
				max_source_bytes=self.limits.max_source_bytes,
				max_ast_nodes=self.limits.max_ast_nodes,
				max_ast_depth=self.limits.max_ast_depth,
			)
			module = wasmtime.Module(self.engine, wat)
			self._validate_module(module)
			self._cache[cache_key] = WasmTeam(self, team_name, digest, wat, module)
		return self._cache[cache_key]

	@staticmethod
	def _validate_module(module):
		actual = [(item.module, item.name) for item in module.imports]
		allowed_order = {spec.name: index for index, spec in enumerate(HOST_IMPORTS)}
		actual_names = [name for namespace, name in actual if namespace == "cosmos" and name in allowed_order]
		if (
			len(actual_names) != len(actual)
			or len(set(actual_names)) != len(actual_names)
			or actual_names != sorted(actual_names, key=allowed_order.__getitem__)
			or any(not isinstance(item.type, wasmtime.FuncType) for item in module.imports)
		):
			raise SandboxUnavailableError("generated module has an unexpected import surface")
		exports = tuple(module.exports)
		export_names = {item.name for item in exports}
		valid_exports = all(
			(item.name == "run" and isinstance(item.type, wasmtime.FuncType))
			or (item.name.startswith("__state_") and isinstance(item.type, wasmtime.GlobalType))
			for item in exports
		)
		if "run" not in export_names or not valid_exports:
			raise SandboxUnavailableError("generated module violates the no-memory ABI")


class WasmTeam:
	def __init__(self, runtime: WasmRuntime, name: str, digest: str, wat: str, module):
		self.runtime = runtime
		self.name = name
		self.digest = digest
		self.wat = wat
		self.module = module
		spec_by_name = {spec.name: spec for spec in HOST_IMPORTS}
		self.import_specs = tuple(spec_by_name[item.name] for item in module.imports)
		self.needs_sensed_snapshot = any(spec.name.startswith("sense_") for spec in self.import_specs)

	def create_player(self, entity_id: int, team_tag: str) -> "WasmPlayer":
		seed_material = f"{self.runtime.seed}:{self.name}:{team_tag}:{entity_id}".encode("utf-8")
		seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "little") or 1
		return WasmPlayer(self, seed)


class WasmPlayer:
	"""One isolated Store/Instance per game entity."""

	def __init__(self, team: WasmTeam, seed: int):
		self.team = team
		self._store = wasmtime.Store(team.runtime.engine)
		self._store.set_limits(memory_size=0, table_elements=0, instances=1, tables=0, memories=0)
		self._store.set_fuel(team.runtime.limits.fuel_per_turn)
		self._controller = None
		self._sensed: Sequence = ()
		self._host_calls_remaining = 0
		self._rng_state = int(seed) & MASK64 or 1
		self.aborted_turns = 0
		self.last_fuel_consumed = 0
		imports = [
			wasmtime.Func(
				self._store,
				wasmtime.FuncType([wasmtime.ValType.i64()] * spec.params, [wasmtime.ValType.i64()]),
				self._callback(spec),
			)
			for spec in team.import_specs
		]
		self._instance = wasmtime.Instance(self._store, team.module, imports)
		exports = self._instance.exports(self._store)
		self._run = exports["run"]
		self._state_globals = [
			exports[item.name]
			for item in team.module.exports
			if item.name.startswith("__state_")
		]

	def _callback(self, spec: HostImport):
		def callback(*args):
			if self._host_calls_remaining <= 0:
				raise RuntimeError("host-call budget exhausted")
			self._host_calls_remaining -= 1
			return self._host_call(spec.name, args)
		return callback

	def run(self, controller):
		state_snapshot = [item.value(self._store) for item in self._state_globals]
		rng_snapshot = self._rng_state
		budget = self.team.runtime.limits.fuel_per_turn
		self._controller = controller
		self._host_calls_remaining = self.team.runtime.limits.max_host_calls_per_turn
		try:
			self._sensed = (
				tuple(controller.sense_nearby_entities())
				if self.team.needs_sensed_snapshot else ()
			)
			if len(self._sensed) > self.team.runtime.limits.max_sensed_entities:
				raise RuntimeError("sensed-entity limit exceeded")
			self._store.set_fuel(budget)
			self._run(self._store)
		except Exception as exc:
			for item, value in zip(self._state_globals, state_snapshot):
				item.set_value(self._store, value)
			self._rng_state = rng_snapshot
			self.aborted_turns += 1
			trap_code = getattr(exc, "trap_code", None)
			out_of_fuel = trap_code == wasmtime.TrapCode.OUT_OF_FUEL
			reason = "instruction budget exhausted" if out_of_fuel else f"sandbox trap: {exc}"
			raise SandboxTurnAborted(reason, out_of_fuel=out_of_fuel) from None
		finally:
			try:
				self.last_fuel_consumed = budget - self._store.get_fuel()
			except Exception:
				self.last_fuel_consumed = budget
			self._controller = None
			self._sensed = ()
			self._host_calls_remaining = 0
		return controller

	def _require_controller(self):
		if self._controller is None:
			raise RuntimeError("host API called outside a player turn")
		return self._controller

	def _sense(self, index: int):
		index = int(index)
		if index < 0 or index >= len(self._sensed):
			raise ValueError("sensed entity index is out of range")
		return self._sensed[index]

	def _host_call(self, name: str, args: Tuple[int, ...]) -> int:
		controller = self._require_controller()
		if name == "get_round_num": return int(controller.get_round_num())
		if name == "get_cooldown_turns": return int(controller.get_cooldown_turns())
		if name == "get_energy": return int(controller.get_energy())
		if name == "get_defence": return int(controller.get_defence())
		if name == "get_id": return int(controller.get_id())
		if name == "get_location": return _pack_location(controller.get_location())
		if name == "get_team": return _team_code(controller.get_team())
		if name == "get_type": return _type_code(controller.get_type())
		if name == "get_radio": return int(controller.get_radio())
		if name == "get_charge_point": return int(controller.get_charge_point())
		if name == "get_entity_count": return int(controller.get_entity_count())
		if name == "is_ready": return int(controller.is_ready())
		if name == "is_opponent":
			team_tag = "Neutral" if int(args[0]) == -1 else str(int(args[0]))
			return int(controller.is_opponent(Team(team_tag)))
		if name == "is_blocked": return int(controller.is_blocked(_unpack_direction(args[0])))
		if name == "is_location_occupied": return int(controller.is_location_occupied(_unpack_location(args[0])))
		if name == "on_the_map": return int(controller.on_the_map(_unpack_location(args[0])))
		if name == "can_detect_location": return int(controller.can_detect_location(_unpack_location(args[0])))
		if name == "can_detect_radius": return int(controller.can_detect_radius(int(args[0])))
		if name == "can_sense_location": return int(controller.can_sense_location(_unpack_location(args[0])))
		if name == "can_sense_radius": return int(controller.can_sense_radius(int(args[0])))
		if name == "can_charge": return int(controller.can_charge(int(args[0])))
		if name == "can_build": return int(controller.can_build(_entity_type(args[0]), _unpack_direction(args[1]), int(args[2])))
		if name == "can_overdrive": return int(controller.can_overdrive(int(args[0])))
		if name == "can_analyze_id": return int(controller.can_analyze(int(args[0])))
		if name == "can_analyze_location": return int(controller.can_analyze(_unpack_location(args[0])))
		if name == "can_move": return int(controller.can_move(_unpack_direction(args[0])))
		if name == "can_set_radio": return int(controller.can_set_radio(int(args[0])))
		if name == "charge": controller.charge(int(args[0])); return 0
		if name == "build": controller.build(_entity_type(args[0]), _unpack_direction(args[1]), int(args[2])); return 0
		if name == "overdrive": controller.overdrive(int(args[0])); return 0
		if name == "analyze_id": controller.analyze(int(args[0])); return 0
		if name == "analyze_location": controller.analyze(_unpack_location(args[0])); return 0
		if name == "move": controller.move(_unpack_direction(args[0])); return 0
		if name == "set_radio": controller.set_radio(int(args[0])); return 0
		if name == "sense_count": return len(self._sensed)
		if name == "sense_id": return int(self._sense(args[0]).ID)
		if name == "sense_energy": return int(self._sense(args[0]).energy)
		if name == "sense_defence": return int(self._sense(args[0]).defence)
		if name == "sense_location": return _pack_location(self._sense(args[0]).location)
		if name == "sense_team": return _team_code(self._sense(args[0]).team)
		if name == "sense_type": return _type_code(self._sense(args[0]).type)
		if name == "sense_radio": return int(self._sense(args[0]).radio)
		if name == "location_make": return _pack_location(MapLocation(int(args[0]), int(args[1])))
		if name == "location_x": return int(_unpack_location(args[0]).x)
		if name == "location_y": return int(_unpack_location(args[0]).y)
		if name == "location_add": return _pack_location(_unpack_location(args[0]).add(_unpack_direction(args[1])))
		if name == "location_subtract": return _pack_location(_unpack_location(args[0]).subtract(_unpack_direction(args[1])))
		if name == "location_translate": return _pack_location(_unpack_location(args[0]).translate(int(args[1]), int(args[2])))
		if name == "location_direction_to": return _pack_direction(_unpack_location(args[0]).direction_to(_unpack_location(args[1])))
		if name == "location_distance_to": return int(_unpack_location(args[0]).distance_to(_unpack_location(args[1])))
		if name == "location_is_adjacent_to": return int(_unpack_location(args[0]).is_adjacent_to(_unpack_location(args[1])))
		if name == "direction_make": return _pack_direction(Direction(int(args[0]), int(args[1])))
		if name == "direction_dx": return int(_unpack_direction(args[0]).dx)
		if name == "direction_dy": return int(_unpack_direction(args[0]).dy)
		if name == "direction_opposite": return _pack_direction(_unpack_direction(args[0]).opposite())
		if name == "direction_rotate_left": return _pack_direction(_unpack_direction(args[0]).rotate_left())
		if name == "direction_rotate_right": return _pack_direction(_unpack_direction(args[0]).rotate_right())
		if name == "direction_all_at": return _pack_direction(Direction(*ALL_DIRECTIONS[int(args[0])]))
		if name == "direction_cardinal_at": return _pack_direction(Direction(*CARDINAL_DIRECTIONS[int(args[0])]))
		if name == "type_action_radius": return self._type_attribute(args[0], TYPE_ACTION_RADIUS)
		if name == "type_detection_radius": return self._type_attribute(args[0], TYPE_DETECTION_RADIUS)
		if name == "type_initial_cooldown": return self._type_attribute(args[0], TYPE_INITIAL_COOLDOWN)
		if name == "type_sensor_radius": return self._type_attribute(args[0], TYPE_SENSOR_RADIUS)
		if name == "random_int": return self._random_int(args[0])
		raise RuntimeError(f"unimplemented host function {name}")

	@staticmethod
	def _type_attribute(value: int, values: Sequence[int]) -> int:
		value = int(value)
		if value < 0 or value >= len(values):
			raise ValueError("invalid encoded entity type")
		return int(values[value])

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

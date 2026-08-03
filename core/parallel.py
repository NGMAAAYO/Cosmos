"""Persistent multi-process decision workers backed by a shared round snapshot.

The parent process is the only authority that mutates game state.  Workers read
an immutable snapshot, run one persistent Player instance per entity, and
return a primitive decision description.  A work item contains only an entity
ID; static map data and all per-round state live in shared memory.
"""

from __future__ import annotations

import hashlib
import importlib
import multiprocessing
import os
import queue
import random
import struct
import traceback
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Dict, Iterable, NamedTuple, Optional, Tuple


_MAGIC = b"COSMOSP1"
_VERSION = 1
_HEADER = struct.Struct("<8s9q")
_INT64 = struct.Struct("<q")
_FLOAT64 = struct.Struct("<d")
_OVERDRIVE = struct.Struct("<3q")
# ID, generation, energy, defence, initial defence, x, y, team, type,
# radio, created round, created planet, cooldown.
_ENTITY = struct.Struct("<12qd")

_TYPE_NAMES = ("planet", "destroyer", "miner", "scout")
_TYPE_CODES = {name: index for index, name in enumerate(_TYPE_NAMES)}


def _team_code(team) -> int:
	tag = team.tag if hasattr(team, "tag") else str(team)
	return -1 if tag == "Neutral" else int(tag)


def _team_name(code: int) -> str:
	return "Neutral" if code == -1 else str(code)


def _stable_seed(*values: int) -> int:
	digest = hashlib.blake2b(digest_size=16, person=b"cosmos-worker")
	for value in values:
		digest.update(int(value).to_bytes(16, "little", signed=True))
	return int.from_bytes(digest.digest(), "little")


def _worker_index(entity_id: int, generation: int, worker_count: int) -> int:
	"""Deterministic SplitMix64 shard selection; never use randomized hash()."""
	value = (int(entity_id) ^ (int(generation) * 0x9E3779B97F4A7C15)) & ((1 << 64) - 1)
	value = (value + 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
	value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
	value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & ((1 << 64) - 1)
	return int((value ^ (value >> 31)) % worker_count)


@dataclass(frozen=True)
class SnapshotSpec:
	name: str
	size: int
	team_capacity: int
	entity_capacity: int
	overdrive_capacity: int
	width: int
	height: int
	team_offset: int
	charge_offset: int
	overdrive_offset: int
	entity_offset: int
	map_offset: int


class DecisionResult(NamedTuple):
	round_number: int
	entity_id: int
	generation: int
	team_code: int
	entity_type: str
	updated_radio: int
	cooldown_cost: float
	primary_action: Optional[Tuple]
	charge_bid: int
	charge_cost: int
	error: Optional[str] = None


class SharedRoundSnapshot:
	"""Parent-owned shared memory containing one immutable published round."""

	def __init__(self, game) -> None:
		width = int(game.map.width)
		height = int(game.map.height)
		entity_capacity = max(1, width * height, len(game.available_entities_ids))
		# Maps may contain Neutral planets in addition to every player team.
		team_capacity = max(1, len(game.team_names), len(game.all_teams))
		# Bonuses expire after 50 rounds.  At most one bonus can be produced per
		# live map cell per round, which gives a safe fixed upper bound.
		overdrive_capacity = max(1, entity_capacity * 50)

		team_offset = _HEADER.size
		charge_offset = team_offset + team_capacity * _INT64.size
		overdrive_offset = charge_offset + team_capacity * _INT64.size
		entity_offset = overdrive_offset + overdrive_capacity * _OVERDRIVE.size
		map_offset = entity_offset + entity_capacity * _ENTITY.size
		size = map_offset + width * height * _FLOAT64.size

		self._memory = shared_memory.SharedMemory(create=True, size=size)
		self._buffer = self._memory.buf
		self.spec = SnapshotSpec(
			name=self._memory.name,
			size=size,
			team_capacity=team_capacity,
			entity_capacity=entity_capacity,
			overdrive_capacity=overdrive_capacity,
			width=width,
			height=height,
			team_offset=team_offset,
			charge_offset=charge_offset,
			overdrive_offset=overdrive_offset,
			entity_offset=entity_offset,
			map_offset=map_offset,
		)
		self._closed = False
		self._write_static_map(game.map)

	def _write_static_map(self, game_map) -> None:
		content = game_map.content
		for x in range(self.spec.width):
			for y in range(self.spec.height):
				offset = self.spec.map_offset + (x * self.spec.height + y) * _FLOAT64.size
				_FLOAT64.pack_into(self._buffer, offset, float(content[x][y]))

	def publish(self, game) -> None:
		entity_count = len(game.available_entities_ids)
		overdrive_count = len(game.overdrive_factor)
		if entity_count > self.spec.entity_capacity:
			raise RuntimeError("实体数量超过共享快照容量。")
		if overdrive_count > self.spec.overdrive_capacity:
			raise RuntimeError("过载增益数量超过共享快照容量。")
		if len(game.charge_result) > self.spec.team_capacity:
			raise RuntimeError("队伍数量超过共享快照容量。")

		for index in range(self.spec.team_capacity):
			team_value = -2
			if index < len(game.all_teams):
				team_value = _team_code(game.all_teams[index])
			_INT64.pack_into(
				self._buffer,
				self.spec.team_offset + index * _INT64.size,
				team_value,
			)
			charge_value = game.charge_result[index] if index < len(game.charge_result) else 0
			_INT64.pack_into(
				self._buffer,
				self.spec.charge_offset + index * _INT64.size,
				int(charge_value),
			)

		for index, factor in enumerate(game.overdrive_factor):
			_OVERDRIVE.pack_into(
				self._buffer,
				self.spec.overdrive_offset + index * _OVERDRIVE.size,
				-1 if factor[0] == "Neutral" else int(factor[0]),
				int(factor[1]),
				int(factor[2]),
			)

		for index, entity_id in enumerate(game.available_entities_ids):
			entity = game.entities[entity_id]
			info = entity.info
			_ENTITY.pack_into(
				self._buffer,
				self.spec.entity_offset + index * _ENTITY.size,
				int(entity_id),
				int(game.entity_generations[entity_id]),
				int(info.energy),
				int(info.defence),
				int(info.init_defence),
				int(info.location.x),
				int(info.location.y),
				_team_code(info.team),
				_TYPE_CODES[info.type.name],
				int(info.radio),
				int(entity.created_round),
				int(entity.created_planet),
				float(entity.cooldown),
			)

		# Publish the header last.  Queueing entity IDs happens after this write;
		# the parent never mutates the buffer until every result has returned.
		_HEADER.pack_into(
			self._buffer,
			0,
			_MAGIC,
			_VERSION,
			int(game.round),
			entity_count,
			len(game.all_teams),
			overdrive_count,
			self.spec.width,
			self.spec.height,
			int(game.map.dx),
			int(game.map.dy),
		)

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		try:
			self._buffer.release()
		except (AttributeError, ValueError):
			pass
		self._memory.close()
		try:
			self._memory.unlink()
		except FileNotFoundError:
			pass


@dataclass
class _SnapshotView:
	round_number: int
	entities: Dict[int, object]
	entity_index: object
	all_teams: list
	charge_result: list
	overdrive_factor: list
	generations: Dict[int, int]
	team_codes: Dict[int, int]


class _SnapshotReader:
	def __init__(self, spec: SnapshotSpec) -> None:
		from core import Map

		self.spec = spec
		self._memory = shared_memory.SharedMemory(name=spec.name)
		self._buffer = self._memory.buf
		blocks = []
		for x in range(spec.width):
			for y in range(spec.height):
				offset = spec.map_offset + (x * spec.height + y) * _FLOAT64.size
				blocks.append({"x": x, "y": y, "aether": _FLOAT64.unpack_from(self._buffer, offset)[0]})
		# The origin is read from the first published header in load().  Map is
		# created lazily because workers start before the first round is published.
		self._blocks = blocks
		self._map_class = Map
		self._map = None

	def load(self) -> _SnapshotView:
		from core import Entity, EntityIndex, EntityType, MapLocation, Team

		(
			magic,
			version,
			round_number,
			entity_count,
			all_team_count,
			overdrive_count,
			width,
			height,
			dx,
			dy,
		) = _HEADER.unpack_from(self._buffer, 0)
		if magic != _MAGIC or version != _VERSION:
			raise RuntimeError("共享快照尚未发布或版本不匹配。")
		if width != self.spec.width or height != self.spec.height:
			raise RuntimeError("共享快照地图尺寸不匹配。")
		if entity_count > self.spec.entity_capacity or overdrive_count > self.spec.overdrive_capacity:
			raise RuntimeError("共享快照计数越界。")
		if all_team_count > self.spec.team_capacity:
			raise RuntimeError("共享快照队伍计数越界。")

		if self._map is None:
			self._map = self._map_class(self._blocks, (width, height), dx, dy)

		all_teams = []
		for index in range(all_team_count):
			code = _INT64.unpack_from(
				self._buffer,
				self.spec.team_offset + index * _INT64.size,
			)[0]
			all_teams.append(Team(_team_name(code)))
		charge_result = [
			int(_INT64.unpack_from(
				self._buffer,
				self.spec.charge_offset + index * _INT64.size,
			)[0])
			for index in range(self.spec.team_capacity)
		]
		overdrive_factor = []
		for index in range(overdrive_count):
			team_code, energy, expires = _OVERDRIVE.unpack_from(
				self._buffer,
				self.spec.overdrive_offset + index * _OVERDRIVE.size,
			)
			overdrive_factor.append((_team_name(team_code), int(energy), int(expires)))

		entities = {}
		generations = {}
		team_codes = {}
		entity_ids = []
		entity_index = EntityIndex()
		for index in range(entity_count):
			(
				entity_id,
				generation,
				energy,
				defence,
				initial_defence,
				x,
				y,
				team_code,
				type_code,
				radio,
				created_round,
				created_planet,
				cooldown,
			) = _ENTITY.unpack_from(
				self._buffer,
				self.spec.entity_offset + index * _ENTITY.size,
			)
			if type_code < 0 or type_code >= len(_TYPE_NAMES):
				raise RuntimeError("共享快照包含未知实体类型。")
			entity = Entity(
				EntityType(_TYPE_NAMES[type_code]),
				int(energy),
				MapLocation(int(x), int(y)),
				Team(_team_name(team_code)),
				int(created_round),
				None if created_planet < 0 else int(created_planet),
				int(entity_id),
			)
			entity.info.defence = int(defence)
			entity.info.init_defence = int(initial_defence)
			entity.info.radio = int(radio)
			entity.cooldown = float(cooldown)
			entities[int(entity_id)] = entity
			generations[int(entity_id)] = int(generation)
			team_codes[int(entity_id)] = int(team_code)
			entity_ids.append(int(entity_id))
			entity_index.add(entity.info)
		entity_index.set_order(entity_ids)
		return _SnapshotView(
			round_number=int(round_number),
			entities=entities,
			entity_index=entity_index,
			all_teams=all_teams,
			charge_result=charge_result,
			overdrive_factor=overdrive_factor,
			generations=generations,
			team_codes=team_codes,
		)

	@property
	def game_map(self):
		return self._map

	def close(self) -> None:
		try:
			self._buffer.release()
		except (AttributeError, ValueError):
			pass
		self._memory.close()


def _serialize_decision(
	view: _SnapshotView,
	entity_id: int,
	controller,
) -> DecisionResult:
	entity = view.entities[entity_id]
	baseline = entity.info
	updated, updated_cooldown, actions = controller.get_actions()
	primary_action = None
	charge_bid = -1
	for action in actions:
		name = str(action[0])
		if name == "charge":
			charge_bid = int(action[1])
			continue
		if primary_action is not None:
			raise RuntimeError("一个单位同一回合返回了多个主要动作。")
		if name == "create":
			params = action[1]
			primary_action = (
				"create",
				str(params[0].name),
				int(params[1].dx),
				int(params[1].dy),
				int(params[2]),
			)
		elif name == "overdrive":
			primary_action = ("overdrive", int(action[1]))
		elif name == "analyze":
			primary_action = ("analyze", int(action[1].ID))
		else:
			raise RuntimeError(f"未知动作：{name}")

	baseline_location = (int(baseline.location.x), int(baseline.location.y))
	updated_location = (int(updated.location.x), int(updated.location.y))
	if updated_location != baseline_location:
		if primary_action is not None:
			raise RuntimeError("一个单位同一回合同时移动并执行了其他主要动作。")
		primary_action = (
			"move",
			updated_location[0] - baseline_location[0],
			updated_location[1] - baseline_location[1],
		)
	create_energy = (
		int(primary_action[4])
		if primary_action is not None and primary_action[0] == "create"
		else 0
	)

	return DecisionResult(
		round_number=view.round_number,
		entity_id=entity_id,
		generation=view.generations[entity_id],
		team_code=view.team_codes[entity_id],
		entity_type=str(baseline.type.name),
		updated_radio=int(updated.radio),
		cooldown_cost=max(float(updated_cooldown) - float(entity.cooldown), 0.0),
		primary_action=primary_action,
		charge_bid=charge_bid,
		charge_cost=max(int(baseline.energy) - int(updated.energy) - create_energy, 0),
	)


@dataclass
class _PlayerSlot:
	generation: int
	team_code: int
	player: object
	random_state: object


def _error_result(view: _SnapshotView, entity_id: int, message: str) -> DecisionResult:
	entity = view.entities[entity_id]
	info = entity.info
	return DecisionResult(
		round_number=view.round_number,
		entity_id=entity_id,
		generation=view.generations[entity_id],
		team_code=view.team_codes[entity_id],
		entity_type=str(info.type.name),
		updated_radio=int(info.radio),
		cooldown_cost=0.0,
		primary_action=None,
		charge_bid=-1,
		charge_cost=0,
		error=message,
	)


def _worker_main(
	worker_number: int,
	team_names: Tuple[str, ...],
	spec: SnapshotSpec,
	task_queue,
	result_queue,
	base_seed: int,
) -> None:
	reader = None
	try:
		random.seed(_stable_seed(base_seed, worker_number, -1))
		team_modules = [importlib.import_module(f"src.{team}.main") for team in team_names]
		reader = _SnapshotReader(spec)
		view = None
		slots: Dict[int, _PlayerSlot] = {}
		while True:
			entity_id = task_queue.get()
			if entity_id is None:
				break
			entity_id = int(entity_id)
			header = _HEADER.unpack_from(reader._buffer, 0)
			published_round = int(header[2])
			if view is None or view.round_number != published_round:
				view = reader.load()
				for stale_id in tuple(slots):
					if (
						stale_id not in view.entities
						or slots[stale_id].generation != view.generations[stale_id]
						or slots[stale_id].team_code != view.team_codes[stale_id]
					):
						del slots[stale_id]

			if entity_id not in view.entities:
				raise RuntimeError(f"worker 收到快照中不存在的单位：{entity_id}")
			generation = view.generations[entity_id]
			team_code = view.team_codes[entity_id]
			try:
				if team_code < 0 or team_code >= len(team_modules):
					raise RuntimeError("中立或未知队伍实体不能执行玩家代码。")
				slot = slots.get(entity_id)
				if slot is None:
					initial_rng = random.Random(
						_stable_seed(base_seed, entity_id, generation, team_code),
					)
					random.setstate(initial_rng.getstate())
					player = team_modules[team_code].Player()
					slot = _PlayerSlot(
						generation=generation,
						team_code=team_code,
						player=player,
						random_state=random.getstate(),
					)
					slots[entity_id] = slot
				random.setstate(slot.random_state)
				entity = view.entities[entity_id]
				controller = entity.get_indexed_controller(
					view.entity_index,
					view.all_teams,
					view.charge_result,
					reader.game_map,
					view.round_number,
					view.overdrive_factor,
				)
				returned_controller = slot.player.run(controller)
				if returned_controller is not controller:
					raise RuntimeError("Player.run 必须返回引擎提供的 Controller 实例。")
				result = _serialize_decision(view, entity_id, controller)
			except BaseException:
				result = _error_result(view, entity_id, traceback.format_exc())
			finally:
				if entity_id in slots:
					slots[entity_id].random_state = random.getstate()
			result_queue.put(result)
	finally:
		if reader is not None:
			reader.close()


class PersistentDecisionWorkers:
	"""Spawn-safe, persistent worker pool with deterministic entity affinity."""

	def __init__(self, game, worker_count: int, base_seed: int) -> None:
		self.worker_count = int(worker_count)
		self.base_seed = int(base_seed)
		self.snapshot = SharedRoundSnapshot(game)
		self._context = multiprocessing.get_context("spawn")
		self._result_queue = self._context.Queue()
		self._task_queues = [self._context.Queue() for _ in range(self.worker_count)]
		self._processes = []
		self._closed = False

		old_hash_seed = os.environ.get("PYTHONHASHSEED")
		os.environ["PYTHONHASHSEED"] = str(self.base_seed % 4_294_967_295)
		try:
			for index in range(self.worker_count):
				process = self._context.Process(
					target=_worker_main,
					args=(
						index,
						tuple(game.team_names),
						self.snapshot.spec,
						self._task_queues[index],
						self._result_queue,
						self.base_seed,
					),
					name=f"cosmos-decision-{index}",
				)
				process.start()
				self._processes.append(process)
		except BaseException:
			self.close()
			raise
		finally:
			if old_hash_seed is None:
				os.environ.pop("PYTHONHASHSEED", None)
			else:
				os.environ["PYTHONHASHSEED"] = old_hash_seed

	def decide(self, game, entity_ids: Iterable[int]) -> Dict[int, DecisionResult]:
		entity_ids = list(entity_ids)
		if len(entity_ids) != len(set(entity_ids)):
			raise RuntimeError("同一轮不能重复提交同一个单位。")
		missing_ids = [
			entity_id for entity_id in entity_ids
			if entity_id not in game.entities or entity_id not in game.entity_generations
		]
		if missing_ids:
			raise RuntimeError(f"共享快照缺少待决策单位：{missing_ids}")
		self.snapshot.publish(game)
		for entity_id in entity_ids:
			generation = game.entity_generations[entity_id]
			index = _worker_index(entity_id, generation, self.worker_count)
			# Per the worker protocol, the only per-unit input is its integer ID.
			self._task_queues[index].put(int(entity_id))

		results = {}
		while len(results) < len(entity_ids):
			try:
				result = self._result_queue.get(timeout=0.25)
			except queue.Empty:
				dead = [process for process in self._processes if not process.is_alive()]
				if dead:
					raise RuntimeError(
						"决策 worker 异常退出：" + ", ".join(
							f"{process.name}({process.exitcode})" for process in dead
						),
					)
				continue
			if result.round_number != game.round:
				raise RuntimeError("决策 worker 返回了过期回合结果。")
			if result.entity_id not in game.entity_generations:
				continue
			if result.entity_id in results:
				raise RuntimeError("决策 worker 重复返回同一单位结果。")
			results[result.entity_id] = result
		return results

	def close(self) -> None:
		if self._closed:
			return
		self._closed = True
		for task_queue in self._task_queues:
			try:
				task_queue.put(None)
			except (OSError, ValueError):
				pass
		for process in self._processes:
			process.join(timeout=2)
			if process.is_alive():
				process.terminate()
				process.join(timeout=2)
		for task_queue in self._task_queues:
			task_queue.close()
			task_queue.join_thread()
		self._result_queue.close()
		self._result_queue.join_thread()
		self.snapshot.close()

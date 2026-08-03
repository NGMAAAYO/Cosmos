import importlib
import hashlib
import random
import math
import time
import json
import os
from tqdm import tqdm
from typing import List, Tuple, Optional

from core import Direction, MapLocation, EntityType, EntityInfo, Team, Map, Controller, Entity, EntityIndex
from core.cosmos_core import (
	engine_get_overdrive_factor, engine_process_overdrive,
	engine_compute_miner_income, engine_process_charge, engine_check_round_end,
	engine_replay_round
)

SPATIAL_INDEX_THRESHOLD = 128


# 定义比赛示例的类
class Instance:
	def __init__(self, teams: List[str], map_path: str, game_round: int, debug: bool = False, show_progress: bool = True, parallel_cores: int = 1) -> None:
		self.team_names = teams
		self.game_round = game_round
		self.show_progress = show_progress
		try:
			requested_cores = int(parallel_cores)
		except (TypeError, ValueError) as exc:
			raise ValueError("parallel_cores 必须是正整数。") from exc
		if requested_cores < 1:
			raise ValueError("parallel_cores 必须是正整数。")
		self.parallel_cores = min(requested_cores, os.cpu_count() or 1)
		self.round = 0
		self.map = None
		self.entities = {}  # 所有的实体
		self.available_entities_ids = []  # 还在场上的实体的ID
		self.entity_infos = []  # 与 available_entities_ids 同序的实体信息视图
		self.entity_index = EntityIndex()  # 增量维护的实体空间索引
		self.deleted_entities_ids = set()  # 本轮已经删除的实体的ID
		self.charge_result = [0] * len(teams)  # 存储充能结果的对象
		self.charge_list = []
		self.overdrive_factor = []  # 过载加成系数，[队伍tag，能量，过期轮数]
		self.planet_list = []  # 存储所有星球的索引
		self.all_teams = []
		self.replay = {"rounds": []}  # 保存回放的对象。应为{map:[], rounds:[], winner:"", reason:""}
		self.entity_instances = {}  # 存储实体实例的字典
		self.entity_generations = {}
		self._next_entity_generation = 0
		self._parallel_runtime = None
		self.team_instances = []
		if self.parallel_cores == 1:
			for team in teams:  # 单核模式保留原有的主进程导入与执行行为
				self.team_instances.append(importlib.import_module(f"src.{team}.main"))

		self.init_map(map_path)  # 初始化地图
		seed_material = repr(random.getstate()).encode("utf-8")
		self._parallel_seed = int.from_bytes(
			hashlib.blake2b(seed_material, digest_size=8, person=b"cosmos-mp").digest(),
			"little",
		)
		self.replay_path = "./replays/replays-{}.rpl".format(int(time.time()))  # 回放存储的位置
		self.debug = debug
		self.game_end_flag = False

	# 计算过载系数
	def get_overdrive_factor(self, team: Team) -> float:
		return engine_get_overdrive_factor(self.overdrive_factor, team.tag, self.round)

	def init_map(self, map_path: str) -> None:
		f = open(map_path, "r", encoding="utf-8")
		fmap = json.loads(f.read())  # 读取json格式的地图
		f.close()

		if len(self.team_names) != fmap["players"]:  # 检查地图配置
			raise Exception("地图配置与玩家数量不匹配。")

		dx = random.randint(-300, 300)
		dy = random.randint(-300, 300)  # 随机偏移
		self.map = Map(fmap["map"], fmap["map_size"], dx, dy)  # 初始化地图对象
		self.replay["map"] = self.map.to_dict()  # 获得地图信息
		for planet in fmap["planets"]:  # 生成初始星球实体
			if planet["team"] not in self.all_teams:  # 保存所有队伍
				self.all_teams.append(Team(planet["team"]))
			self.planet_list.append(self.add_entity(EntityType("planet"), planet["energy"], MapLocation(planet["x"], planet["y"]).translate(dx, dy), Team(planet["team"])))

	def add_entity(self, entity_type: EntityType, energy: int, location: MapLocation, team: Team, planet: Optional[int] = None) -> int:
		if not self.map.include(*location.to_tuple()):
			raise Exception("尝试在地图外生成实体。")
		rid = random.randint(10000, 99999)
		while rid in self.entities:  # 生成唯一ID
			rid = random.randint(10000, 99999)

		entity = Entity(entity_type, energy, location, team, self.round, planet, rid)
		self.entities[rid] = entity  # 添加新的实体
		self._next_entity_generation += 1
		self.entity_generations[rid] = self._next_entity_generation
		self.available_entities_ids.append(rid)
		self.entity_infos.append(entity.info)
		self.entity_index.add(entity.info)
		if team != "Neutral" and self.parallel_cores == 1:
			self.entity_instances[rid] = self.team_instances[int(team.tag)].Player()  # 对应队伍的实例
		return rid

	def remove_entity(self, entity_id: int) -> None:
		entity_index = self.available_entities_ids.index(entity_id)
		self.entity_index.remove(entity_id)
		self.available_entities_ids.pop(entity_index)
		self.entity_infos.pop(entity_index)
		self.deleted_entities_ids.add(entity_id)
		del self.entities[entity_id]
		self.entity_instances.pop(entity_id, None)
		self.entity_generations.pop(entity_id, None)

	def _reset_entity_player(self, entity_id: int, team_tag: str) -> None:
		self._next_entity_generation += 1
		self.entity_generations[entity_id] = self._next_entity_generation
		if self.parallel_cores == 1:
			self.entity_instances[entity_id] = self.team_instances[int(team_tag)].Player()

	# 管理全局回合的方法。
	def run(self) -> Tuple[str, str, str]:
		self.new_replay()  # 初始化
		looper = range(self.game_round)
		if self.show_progress:
			looper = tqdm(looper)
			
		try:
			for _ in looper:  # 执行回合循环
				if self.show_progress:
					looper.set_postfix_str("Entity: {}".format(len(self.available_entities_ids)))
				self.next_round()
				if self.game_end_flag:
					return self.replay["winner"], self.replay["reason"], self.replay_path

			self.counting_result()  # 统计比赛数据
			return self.replay["winner"], self.replay["reason"], self.replay_path
		finally:
			self.close()

	def next_round(self) -> None:
		self.round += 1
		self.charge_list = []  # 星球充能列表
		self.deleted_entities_ids.clear()  # 重置删除实体集合
		if self.overdrive_factor:
			self.overdrive_factor = [factor for factor in self.overdrive_factor if factor[2] > self.round]
		random.shuffle(self.available_entities_ids)  # 打乱实体的执行顺序
		self.entity_infos = [self.entities[rid].info for rid in self.available_entities_ids]
		self.entity_index.set_order(self.available_entities_ids)

		for p in self.planet_list:
			if self.entities[p].info.team != "Neutral":
				self.entities[p].info.energy += math.ceil(0.2 * math.sqrt(self.round))  # 给每个星球增加资源点

		if self.parallel_cores == 1:
			for rid in self.available_entities_ids.copy():  # 分别运行还在场上的所有实体
				if rid in self.deleted_entities_ids:  # 如果实体已经被删除
					continue
				if self.entities[rid].info.team != "Neutral":  # 忽略中立的实体
					self.entities[rid].cooldown = max(self.entities[rid].cooldown-1, 0)  # 减少冷却
					if self.debug:
						self.run_instance(rid)
					else:
						try:
							self.run_instance(rid)
						except Exception as err:
							print("[Team {}] {}".format(self.entities[rid].info.team, err))
		else:
			self._run_parallel_decisions()
		self.end_round_check()  # 一轮最末尾进行检查，判断游戏是否结束，计算全局变量

	def _ensure_parallel_runtime(self):
		if self._parallel_runtime is None:
			from core.parallel import PersistentDecisionWorkers
			self._parallel_runtime = PersistentDecisionWorkers(
				self,
				self.parallel_cores,
				self._parallel_seed,
			)
		return self._parallel_runtime

	def _run_parallel_decisions(self) -> None:
		round_entity_ids = self.available_entities_ids.copy()
		runnable_ids = []
		for entity_id in round_entity_ids:
			entity = self.entities[entity_id]
			if entity.info.team == "Neutral":
				continue
			entity.cooldown = max(entity.cooldown - 1, 0)
			runnable_ids.append(entity_id)

		if not runnable_ids:
			return
		decisions = self._ensure_parallel_runtime().decide(self, runnable_ids)
		occupied = {
			(entity.info.location.x, entity.info.location.y): entity_id
			for entity_id, entity in self.entities.items()
		}
		for entity_id in round_entity_ids:
			decision = decisions.get(entity_id)
			if decision is None:
				continue
			if decision.error:
				message = decision.error.rstrip().splitlines()[-1]
				if self.debug:
					raise RuntimeError(
						"[Team {}] {}".format(decision.team_code, decision.error.rstrip()),
					)
				print("[Team {}] {}".format(decision.team_code, message))
				continue
			self._commit_parallel_decision(decision, occupied)

	@staticmethod
	def _valid_direction(dx: int, dy: int) -> bool:
		return -1 <= dx <= 1 and -1 <= dy <= 1 and (dx != 0 or dy != 0)

	def _same_parallel_actor(self, decision) -> bool:
		entity = self.entities.get(decision.entity_id)
		if entity is None:
			return False
		return (
			decision.round_number == self.round
			and self.entity_generations.get(decision.entity_id) == decision.generation
			and entity.info.team.tag == str(decision.team_code)
			and entity.info.type.name == decision.entity_type
		)

	def _remove_occupied(self, occupied, entity_id: int) -> None:
		entity = self.entities.get(entity_id)
		if entity is None:
			return
		location = (entity.info.location.x, entity.info.location.y)
		if occupied.get(location) == entity_id:
			occupied.pop(location, None)

	def _execute_parallel_overdrive(self, entity_id: int, radius: int, occupied) -> None:
		entity = self.entities[entity_id]
		attacker = entity.info.copy()
		odfactor = self.get_overdrive_factor(attacker.team)
		self._remove_occupied(occupied, entity_id)
		self.remove_entity(entity_id)
		effects = engine_process_overdrive(
			self.available_entities_ids,
			self.entity_infos,
			attacker,
			radius,
			odfactor,
		)
		for target_id, new_energy, new_defence, new_team, should_remove in effects:
			if target_id not in self.entities:
				continue
			if should_remove:
				self._remove_occupied(occupied, target_id)
				self.remove_entity(target_id)
				continue
			target = self.entities[target_id]
			target.info.energy = new_energy
			target.info.defence = new_defence
			if new_team:
				target.info.team = Team(new_team)
				self._reset_entity_player(target_id, new_team)
				self.entity_index.sync(target_id)

	def _commit_parallel_decision(self, decision, occupied) -> None:
		if not self._same_parallel_actor(decision):
			return
		entity_id = decision.entity_id
		entity = self.entities[entity_id]
		info = entity.info
		if 0 <= decision.updated_radio <= (1 << 28) - 1:
			info.radio = decision.updated_radio

		action = decision.primary_action
		cooldown_cost = decision.cooldown_cost
		if action is not None and action[0] == "move":
			dx, dy = int(action[1]), int(action[2])
			destination = (info.location.x + dx, info.location.y + dy)
			if (
				info.type.name != "planet"
				and entity.cooldown < 1
				and self._valid_direction(dx, dy)
				and self.map.include(*destination)
				and occupied.get(destination) in (None, entity_id)
			):
				self._remove_occupied(occupied, entity_id)
				info.location = MapLocation(*destination)
				occupied[destination] = entity_id
				entity.cooldown += cooldown_cost
				self.entity_index.sync(entity_id)

		elif action is not None and action[0] == "create":
			_, type_name, dx, dy, energy = action
			dx, dy, energy = int(dx), int(dy), int(energy)
			destination = (info.location.x + dx, info.location.y + dy)
			if (
				info.type.name == "planet"
				and type_name in {"destroyer", "miner", "scout"}
				and entity.cooldown < 1
				and self._valid_direction(dx, dy)
				and energy > 0
				and info.energy >= energy
				and self.map.include(*destination)
				and occupied.get(destination) is None
			):
				info.energy -= energy
				entity.cooldown += cooldown_cost
				created_id = self.add_entity(
					EntityType(type_name),
					energy,
					MapLocation(*destination),
					info.team,
					info.ID,
				)
				occupied[destination] = created_id

		elif action is not None and action[0] == "analyze":
			target = self.entities.get(int(action[1]))
			if (
				info.type.name == "scout"
				and entity.cooldown < 1
				and info.defence >= 10
				and target is not None
				and target.info.type.name == "miner"
				and target.info.team != info.team
				and target.info.location.distance_to(info.location) <= info.type.action_radius
			):
				target_energy = target.info.energy
				self._remove_occupied(occupied, target.info.ID)
				self.remove_entity(target.info.ID)
				info.defence -= 10
				entity.cooldown += cooldown_cost
				self.overdrive_factor.append((info.team.tag, target_energy, self.round + 50))

		elif action is not None and action[0] == "overdrive":
			radius = int(action[1])
			if (
				info.type.name == "destroyer"
				and entity.cooldown < 1
				and 0 <= radius <= info.type.action_radius
			):
				# Overdrive has no fixed target and is never cancelled because a
				# unit observed in the snapshot has since moved out of range.
				self._execute_parallel_overdrive(entity_id, radius, occupied)

		if entity_id not in self.entities:
			return
		entity = self.entities[entity_id]
		info = entity.info

		if info.type.name == "planet" and decision.charge_bid >= 0:
			if info.energy >= decision.charge_cost and decision.charge_bid <= decision.charge_cost:
				info.energy -= decision.charge_cost
				self.charge_list.append((entity_id, int(decision.charge_bid)))
			else:
				self.charge_list.append((entity_id, 0))
			info.defence = info.energy

		if (
			info.type.name == "miner"
			and self.round >= entity.created_round + 50
		):
			created_planet = self.entities.get(entity.created_planet)
			if created_planet is not None and created_planet.info.team == info.team:
				created_planet.info.energy += engine_compute_miner_income(info.energy)

	def close(self) -> None:
		if self._parallel_runtime is not None:
			self._parallel_runtime.close()
			self._parallel_runtime = None

	def __del__(self):
		try:
			self.close()
		except Exception:
			pass

	def run_instance(self, entity_id: int) -> None:
		entity = self.entities[entity_id]  # 获取实体
		if len(self.available_entities_ids) >= SPATIAL_INDEX_THRESHOLD:
			controller = entity.get_indexed_controller(self.entity_index, self.all_teams, self.charge_result, self.map, self.round, self.overdrive_factor)
		else:
			controller = entity.get_controller(self.entity_infos, self.all_teams, self.charge_result, self.map, self.round, self.overdrive_factor)  # 获取控制器，传入副本
		returned_controller = self.entity_instances[entity_id].run(controller)  # 运行玩家实例
		if returned_controller is not controller:
			raise RuntimeError("Player.run 必须返回引擎提供的 Controller 实例。")
		self.end_instance_check(entity_id, controller)  # 玩家行动后进行检查，更新全局与本地实体状态

	def end_instance_check(self, entity_id: int, controller: Controller) -> None:
		self.entities[entity_id].info, self.entities[entity_id].cooldown, actions = controller.get_actions()  # 更新本地实体状态
		self.entity_index.sync(entity_id)
		local_info = self.entities[entity_id].info
		for action in actions:
			if action[0] == "create":  # 创造新的实体，参数为(type, dir, energy)
				canonical_type = EntityType(action[1][0].name)
				_ = self.add_entity(canonical_type, action[1][2], local_info.location.add(action[1][1]), local_info.team, local_info.ID)
			elif action[0] == "charge":  # 充能，参数为 energy
				self.charge_list.append((entity_id, action[1]))  # 保存id，等到回合结束后比较
			elif action[0] == "overdrive":  # 过载，参数为 radius
				self.remove_entity(entity_id)  # 过载后删除本实体
				# 使用C++引擎计算过载效果
				odfactor = self.get_overdrive_factor(local_info.team)
				effects = engine_process_overdrive(self.available_entities_ids, self.entity_infos, local_info, action[1], odfactor)
				for rid, new_energy, new_defence, new_team, should_remove in effects:
					if should_remove:
						self.remove_entity(rid)
					else:
						self.entities[rid].info.energy = new_energy
						self.entities[rid].info.defence = new_defence
						if new_team:  # 队伍转换
							self.entities[rid].info.team = Team(new_team)
							self._reset_entity_player(rid, new_team)
							self.entity_index.sync(rid)

			elif action[0] == "analyze":  # 分析，参数为 target
				target = self.entities.get(action[1].ID)
				if (local_info.type == "scout" and target is not None and
						target.info.type == "miner" and target.info.team != local_info.team and
						target.info.location.distance_to(local_info.location) <= local_info.type.action_radius):
					target_energy = target.info.energy
					self.remove_entity(target.info.ID)  # 删除实体
					self.overdrive_factor.append((local_info.team.tag, target_energy, self.round + 50))  # 增加增益

		if local_info.type == "miner":  # 开采舰的场合
			if self.round >= self.entities[entity_id].created_round + 50:  # 如果已经超过了50回合
				created_planet_index = self.entities[entity_id].created_planet
				if self.entities[created_planet_index].info.team == local_info.team:  # 如果母星仍然属于本队
					self.entities[created_planet_index].info.energy += engine_compute_miner_income(local_info.energy)

	def end_round_check(self) -> None:  # 处理开采舰是否进化、计算充能，判断游戏是否结束。
		# 使用C++引擎检查存活队伍和开采舰进化
		ids = list(self.available_entities_ids)
		team_tags = [self.entities[rid].info.team.tag for rid in ids]
		type_names = [self.entities[rid].info.type.name for rid in ids]
		created_rounds = [self.entities[rid].created_round for rid in ids]
		alive_team_tags, evolution_ids = engine_check_round_end(ids, team_tags, type_names, created_rounds, self.round)

		for rid in evolution_ids:
			self.entities[rid].info.type = EntityType("destroyer")

		self.new_replay()  # 保存录像
		if len(alive_team_tags) == 0:
			self.end_game("tie", None)
		elif len(alive_team_tags) == 1:
			self.end_game("eliminate", int(alive_team_tags[0]))  # 结束游戏

		# 使用C++引擎处理充能
		charge_team_tags = [self.entities[c[0]].info.team.tag for c in self.charge_list]
		winner_team, returns = engine_process_charge(self.charge_list, charge_team_tags)
		if winner_team >= 0:
			self.charge_result[winner_team] += 1
		for eid, energy_return in returns:
			self.entities[eid].info.energy += energy_return

	# 计算比赛结果的方法
	def counting_result(self) -> None:
		max_charge = max(self.charge_result)  # 充能最多的值
		max_charge_team = []
		for i, c in enumerate(self.charge_result):  # 遍历
			if c == max_charge:
				max_charge_team.append(i)
		if len(max_charge_team) == 1:  # 只有一方最大的场合
			self.end_game("final_charge", max_charge_team[0])
		else:
			team_planet_count = [0] * len(self.charge_result)  # 与队伍数等长的对象
			for p in self.planet_list:
				team_tag = self.entities[p].info.team.tag
				if team_tag != "Neutral":
					team_planet_count[int(team_tag)] += 1
			most_planet = max(team_planet_count)  # 最多的星球数
			most_planet_team = []
			for i, c in enumerate(team_planet_count):  # 遍历
				if c == most_planet:
					most_planet_team.append(i)
			if len(most_planet_team) == 1:  # 只有一方最多的场合
				self.end_game("most_planets", most_planet_team[0])
			else:
				team_energy_count = [0] * len(self.charge_result)  # 与队伍数等长的对象
				for e in self.entities.values():
					if e.info.team != "Neutral":
						team_energy_count[int(e.info.team.tag)] += e.info.energy
				most_energy = max(team_energy_count)  # 最多的能量数
				most_energy_team = []
				for i, c in enumerate(team_energy_count):  # 遍历
					if c == most_energy:
						most_energy_team.append(i)
				if len(most_energy_team) == 1:  # 只有一方最多的场合
					self.end_game("most_energy", most_energy_team[0])
				else:
					self.end_game("tie", None)  # 平局

	# 保存这一回合至回放中
	def new_replay(self) -> None:
		self.replay["rounds"].append(engine_replay_round(self.entity_infos))

	def save_replay(self) -> None:
		os.makedirs(os.path.dirname(self.replay_path), exist_ok=True)
		with open(self.replay_path, "w", encoding="utf-8") as f:
			f.write(json.dumps(self.replay))

	# 结束比赛的方法
	def end_game(self, reason: str, winner: Optional[int]) -> None:
		# 保存胜者和胜利原因
		self.replay["winner"] = self.team_names[winner] if winner is not None else "None"
		self.replay["reason"] = reason

		print("胜者：" + self.replay["winner"])
		if reason == "eliminate":
			print("原因：消灭了其他所有的实体。")
		elif reason == "final_charge":
			print("原因：最终兵器有更多的能量点。")
			print(self.charge_result)
		elif reason == "most_planets":
			print("原因：拥有更多的星球。")
		elif reason == "most_energy":
			print("原因：队伍所有实体的总能量更高。")
		else:
			print("原因：平局")

		team_entity_count = [[0, 0, 0, 0] for _ in self.team_names]
		team_energy_count = [[0, 0, 0, 0] for _ in self.team_names]
		neutral_count = 0
		for eid in self.available_entities_ids:
			team_tag = self.entities[eid].info.team.tag
			if team_tag == "Neutral":
				neutral_count += 1
				continue
			team_tag = int(team_tag)
			entity_type = self.entities[eid].info.type.name
			if entity_type == "planet":
				team_entity_count[team_tag][0] += 1
				team_energy_count[team_tag][0] += self.entities[eid].info.energy
			elif entity_type == "destroyer":
				team_entity_count[team_tag][1] += 1
				team_energy_count[team_tag][1] += self.entities[eid].info.energy
			elif entity_type == "miner":
				team_entity_count[team_tag][2] += 1
				team_energy_count[team_tag][2] += self.entities[eid].info.energy
			elif entity_type == "scout":
				team_entity_count[team_tag][3] += 1
				team_energy_count[team_tag][3] += self.entities[eid].info.energy
		

		for t in range(len(self.team_names)):
			print("========\n[Team {}] {} 剩余实体：".format(t, self.team_names[t]))
			print("planet: {} 平均能量：{:.2f}".format(
				team_entity_count[t][0],
				team_energy_count[t][0] / team_entity_count[t][0] if team_entity_count[t][0] != 0 else 0
			))
			print("destroyer: {} 平均能量：{:.2f}".format(
				team_entity_count[t][1],
				team_energy_count[t][1] / team_entity_count[t][1] if team_entity_count[t][1] != 0 else 0
			))
			print("miner: {} 平均能量：{:.2f}".format(
				team_entity_count[t][2],
				team_energy_count[t][2] / team_entity_count[t][2] if team_entity_count[t][2] != 0 else 0
			))
			print("scout: {} 平均能量：{:.2f}".format(
				team_entity_count[t][3],
				team_energy_count[t][3] / team_entity_count[t][3] if team_entity_count[t][3] != 0 else 0
			))

		print("========\n中立实体：{}".format(neutral_count))
		print("回放已保存至：{}".format(self.replay_path))

		self.save_replay()
		self.game_end_flag = True

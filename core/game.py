import importlib
import random
import math
import time
import json
import os
from tqdm import tqdm

from core.api import *
from core.entity import Entity
from core.classes import Map


# 定义比赛示例的类
class Instance:
	def __init__(self, teams, map_path, game_round, debug=False, show_progress=True):
		self.team_names = teams
		self.game_round = game_round
		self.show_progress = show_progress
		self.round = 0
		self.map = None
		self.entities = {}  # 所有的实体
		self.available_entities_ids = []  # 还在场上的实体的ID
		self.deleted_entities_ids = []  # 本轮已经删除的实体的ID
		self.charge_result = [0] * len(teams)  # 存储充能结果的对象
		self.charge_list = []
		self.overdrive_factor = []  # 过载加成系数，[队伍tag，能量，过期轮数]
		self.planet_list = []  # 存储所有星球的索引
		self.all_teams = []
		self.replay = {"rounds": []}  # 保存回放的对象。应为{map:[], rounds:[], winner:"", reason:""}
		self.entity_instances = {}  # 存储实体实例的字典
		self.team_instances = []
		for team in teams:  # 导入玩家的代码
			self.team_instances.append(importlib.import_module(f"src.{team}.main"))

		self.init_map(map_path)  # 初始化地图
		self.replay_path = "./replays/replays-{}.rpl".format(int(time.time()))  # 回放存储的位置
		self.debug = debug
		self.game_end_flag = False

	# 计算过载系数
	def get_overdrive_factor(self, team):
		index = 0
		for i in self.overdrive_factor:
			if i[0] == team.tag and i[2] > self.round:  # 如果是同一队并且过期轮数大于当前轮数，则累加
				index += i[1]
		return (1.0 + 0.001) ** min(1145, index)

	def init_map(self, map_path):
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

	def add_entity(self, entity_type, energy, location, team, planet=None):
		if not self.map.include(*location.to_tuple()):
			raise Exception("尝试在地图外生成实体。")
		rid = random.randint(10000, 99999)
		while str(rid) in list(self.entities.keys()):  # 生成唯一ID
			rid = random.randint(10000, 99999)

		self.entities[str(rid)] = Entity(entity_type, energy, location, team, self.round, planet, rid)  # 添加新的实体
		self.available_entities_ids.append(rid)
		if team != "Neutral":
			self.entity_instances[str(rid)] = self.team_instances[int(team.tag)].Player()  # 对应队伍的实例
		return rid

	def remove_entity(self, entity_id):
		self.available_entities_ids.remove(entity_id)
		self.deleted_entities_ids.append(entity_id)
		del self.entities[str(entity_id)]
		del self.entity_instances[str(entity_id)]

	# 管理全局回合的方法。
	def run(self):
		self.new_replay()  # 初始化
		looper = range(self.game_round)
		if self.show_progress:
			looper = tqdm(looper)
			
		for _ in looper:  # 执行回合循环
			if self.show_progress:
				looper.set_postfix_str("Entity: {}".format(len(self.available_entities_ids)))
			self.next_round()
			if self.game_end_flag:
				return self.replay["winner"], self.replay["reason"], self.replay_path

		self.counting_result()  # 统计比赛数据

		return self.replay["winner"], self.replay["reason"], self.replay_path

	def next_round(self):
		self.round += 1
		self.charge_list = []  # 星球充能列表
		self.deleted_entities_ids = []  # 重置删除实体列表
		random.shuffle(self.available_entities_ids)  # 打乱实体的执行顺序

		for p in self.planet_list:
			if self.entities[str(p)].info.team != "Neutral":
				self.entities[str(p)].info.energy += math.ceil(0.2 * math.sqrt(self.round))  # 给每个星球增加资源点

		for rid in self.available_entities_ids.copy():  # 分别运行还在场上的所有实体
			if rid in self.deleted_entities_ids:  # 如果实体已经被删除
				continue
			if self.entities[str(rid)].info.team != "Neutral":  # 忽略中立的实体
				self.entities[str(rid)].cooldown = max(self.entities[str(rid)].cooldown-1, 0)  # 减少冷却
				if self.debug:
					self.run_instance(rid)
				else:
					try:
						self.run_instance(rid)
					except Exception as err:
						print("[Team {}] {}".format(self.entities[str(rid)].info.team, err))
		self.end_round_check()  # 一轮最末尾进行检查，判断游戏是否结束，计算全局变量

	def run_instance(self, entity_id):
		entity = self.entities[str(entity_id)]  # 获取实体
		all_entities = []
		for rid in self.available_entities_ids:  # 获取当前的在场实体
			all_entities.append(self.entities[str(rid)].info)

		controller = entity.get_controller(all_entities, self.all_teams, self.charge_result, self.map, self.round, self.overdrive_factor)  # 获取控制器，传入副本
		controller = self.entity_instances[str(entity_id)].run(controller)  # 运行玩家实例
		self.end_instance_check(entity_id, controller)  # 玩家行动后进行检查，更新全局与本地实体状态

	def end_instance_check(self, entity_id, controller):
		self.entities[str(entity_id)].info, self.entities[str(entity_id)].cooldown, actions = controller.get_actions()  # 更新本地实体状态
		local_info = self.entities[str(entity_id)].info
		for action in actions:
			if action[0] == "create":  # 创造新的实体，参数为(type, dir, energy)
				_ = self.add_entity(action[1][0], action[1][2], local_info.location.add(action[1][1]), local_info.team, local_info.ID)
			elif action[0] == "charge":  # 充能，参数为 energy
				self.charge_list.append((entity_id, action[1]))  # 保存id，等到回合结束后比较
			elif action[0] == "overdrive":  # 过载，参数为 radius
				self.remove_entity(entity_id)  # 过载后删除本实体
				targets = []
				for rid in self.available_entities_ids:  # 选出所有在半径内的实体
					if self.entities[str(rid)].info.location.distance_to(local_info.location) <= action[1]:
						targets.append(rid)
				if len(targets) != 0 and local_info.defence > 10:  # 注意，过载应该是以防护值为基础值
					base_energy = (local_info.defence - 10) / len(targets)  # 均分能量
					odfactor = self.get_overdrive_factor(local_info.team)  # 获得当前增益系数
					for rid in targets:  # 依次处理
						entity_info = self.entities[str(rid)].info
						if entity_info.team == local_info.team:  # 友军的场合
							if entity_info.type == "planet":
								self.entities[str(rid)].info.energy += int(base_energy * odfactor)
							else:
								self.entities[str(rid)].info.defence += int(base_energy * odfactor)
								self.entities[str(rid)].info.defence = min(self.entities[str(rid)].info.defence, entity_info.init_defence)  # 限制上限
						else:  # 非友军的场合
							if entity_info.type == "planet":
								self.entities[str(rid)].info.energy -= int(base_energy * odfactor)
								if self.entities[str(rid)].info.energy < 0:  # 如果能量值小于零
									self.entities[str(rid)].info.energy = -self.entities[str(rid)].info.energy  # 新实体能量值等于绝对值
									self.entities[str(rid)].info.team = local_info.team  # 转换队伍
									self.entity_instances[str(rid)] = self.team_instances[int(local_info.team.tag)].Player()  # 对应队伍的实例
							else:
								self.entities[str(rid)].info.defence -= int(base_energy * odfactor)
								if entity_info.type == "destroyer":
									if self.entities[str(rid)].info.defence < 0:  # 如果防护值小于零
										self.entities[str(rid)].info.defence = -self.entities[str(rid)].info.defence  # 新实体防护值等于绝对值
										self.entities[str(rid)].info.defence = min(self.entities[str(rid)].info.defence, entity_info.init_defence)  # 限制上限
										self.entities[str(rid)].info.team = local_info.team  # 转换队伍
										self.entity_instances[str(rid)] = self.team_instances[int(local_info.team.tag)].Player()  # 对应队伍的实例
									elif self.entities[str(rid)].info.defence == 0:
										self.remove_entity(entity_info.ID)
								else:
									if self.entities[str(rid)].info.defence <= 0:  # 如果防护值小于零
										self.remove_entity(entity_info.ID)  # 删除实体

			elif action[0] == "analyze":  # 分析，参数为 target
				if action[1].type == "miner" and action[1].team != local_info.team:
					self.remove_entity(action[1].ID)  # 删除实体
					self.overdrive_factor.append((local_info.team.tag, action[1].energy, self.round + 50))  # 增加增益

		if local_info.type == "miner":  # 开采舰的场合
			if self.round >= self.entities[str(entity_id)].created_round + 50:  # 如果已经超过了50回合
				created_planet_index = str(self.entities[str(entity_id)].created_planet)
				if self.entities[created_planet_index].info.team == local_info.team:  # 如果母星仍然属于本队
					self.entities[created_planet_index].info.energy += math.floor((0.02 + 0.03 * math.e ** (-0.001 * local_info.energy)) * local_info.energy)  # 增加资源

	def end_round_check(self):  # 处理开采舰是否进化、计算充能，判断游戏是否结束。
		alive_team = []
		for rid in self.available_entities_ids:
			entity = self.entities[str(rid)]  # 遍历剩余实体
			if entity.info.team not in alive_team:  # 获得还有实体在场的队伍Tag
				alive_team.append(entity.info.team)
			if entity.info.type == "miner":  # 判断进化
				if self.round >= entity.created_round + 300:
					self.entities[str(rid)].info.type = EntityType("destroyer")

		self.new_replay()  # 保存录像
		if len(alive_team) <= 1:
			self.end_game("eliminate", int(alive_team[0].tag))  # 结束游戏

		max_energy = -1  # 计算最大的能量
		for c in self.charge_list:  # 遍历所有星球
			max_energy = max(max_energy, c[1])

		max_planet = []
		for c in self.charge_list:  # 遍历第二次，尝试求出最大值的位置
			if c[1] == max_energy:
				max_planet.append(c[0])  # 收集最大值星球的索引

		for c in self.charge_list:
			if len(max_planet) == 1 and max_planet[0] == c[0]:  # 唯一最大值的场合
				self.charge_result[int(self.entities[str(c[0])].info.team.tag)] += 1  # 充能结果加一
			else:
				self.entities[str(c[0])].info.energy += math.floor(c[1] / 2)  # 返还一半的能量

	# 计算比赛结果的方法
	def counting_result(self):
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
				team_planet_count[int(self.entities[str(p)].info.team.tag)] += 1
			most_planet = max(team_planet_count)  # 最多的星球数
			most_planet_team = []
			for i, c in enumerate(team_planet_count):  # 遍历
				if c == most_planet:
					most_planet_team.append(i)
			if len(most_planet_team) == 1:  # 只有一方最多的场合
				self.end_game("most_planets", most_planet_team[0])
			else:
				team_energy_count = [0] * len(self.charge_result)  # 与队伍数等长的对象
				for e in list(self.entities.values()):
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
	def new_replay(self):
		self.replay["rounds"].append([self.entities[str(rid)].info.to_dict() for rid in self.available_entities_ids])

	def save_replay(self):
		os.makedirs(os.path.dirname(self.replay_path), exist_ok=True)
		with open(self.replay_path, "w", encoding="utf-8") as f:
			f.write(json.dumps(self.replay))

	# 结束比赛的方法
	def end_game(self, reason, winner):
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
			team_tag = self.entities[str(eid)].info.team.tag
			if team_tag == "Neutral":
				neutral_count += 1
				continue
			team_tag = int(team_tag)
			entity_type = self.entities[str(eid)].info.type.name
			if entity_type == "planet":
				team_entity_count[team_tag][0] += 1
				team_energy_count[team_tag][0] += self.entities[str(eid)].info.energy
			elif entity_type == "destroyer":
				team_entity_count[team_tag][1] += 1
				team_energy_count[team_tag][1] += self.entities[str(eid)].info.energy
			elif entity_type == "miner":
				team_entity_count[team_tag][2] += 1
				team_energy_count[team_tag][2] += self.entities[str(eid)].info.energy
			elif entity_type == "scout":
				team_entity_count[team_tag][3] += 1
				team_energy_count[team_tag][3] += self.entities[str(eid)].info.energy
		

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

import importlib
import random
import math
import json

from core.api import *
from core.entity import Entity


# 定义比赛示例的类
class Instance:
	def __init__(self, teams, map_path, game_round):
		self.game_round = game_round
		self.round = 0
		self.map = []
		self.entities = {}  # 所有的实体
		self.available_entities_ids = []  # 还在场上的实体的ID
		self.charge_list = []
		self.overdrive_factor = []  # 过载加成系数，[队伍tag，能量，过期轮数]
		self.team_instances = []
		for team in teams:  # 导入玩家的代码
			self.team_instances.append(importlib.import_module(f"src.{team}.main"))

		self.init_map(map_path)  # 初始化地图

	# 计算过载系数
	def get_overdrive_factor(self, team):
		index = 0
		for i in self.overdrive_factor:
			if i[0] == team.tag and i[2] > self.round:  # 如果是同一队并且过期轮数大于当前轮数，则累加
				index += i[1]
		return (1.0 + 0.001) ** index

	def init_map(self, map_path):
		f = open(map_path, "r", encoding="utf-8")
		fmap = json.loads(f.read())  # 读取json格式的地图
		f.close()

		self.map = fmap["map"]  # 获得地图信息
		for planet in fmap["planets"]:  # 生成初始星球实体
			self.add_entity(EntityType("planet"), planet["energy"], MapLocation(planet["x"], planet["y"]), planet["team"])

	def add_entity(self, entity_type, energy, location, team, planet=None):
		rid = random.randint(10000, 99999)
		while rid in list(self.entities.keys()):  # 生成唯一ID
			rid = random.randint(10000, 99999)

		self.entities[str(rid)] = Entity(entity_type, energy, location, team, self.round, planet, rid)  # 添加新的实体
		self.available_entities_ids.append(rid)

	def next_round(self):
		self.round += 1
		self.charge_list = []  # 星球充能列表
		random.shuffle(self.available_entities_ids)
		for rid in self.available_entities_ids:  # 分别运行还在场上的所有实体
			self.run_instance(rid)

		self.end_round_check()  # 一轮最末尾进行检查，判断游戏是否结束，计算全局变量
		
	def run_instance(self, entity_id):
		try:
			entity = self.entities[str(entity_id)]  # 获取实体
			player = self.team_instances[int(entity.info.team)].Player()  # 实例化玩家的代码
			all_entities = []
			for rid in self.available_entities_ids:  # 获取当前的在场实体
				if rid != entity_id:  # 省略自己
					all_entities.append(self.entities[str(rid)])

			controller = entity.get_controller(all_entities, self.map, self.round, self.overdrive_factor)  # 获取控制器，传给玩家实例
			controller = player.run(controller)  # 运行玩家代码
			self.end_instance_check(entity_id, controller)  # 玩家行动后进行检查，更新全局与本地实体状态
		except Exception as err:
			print("[Team {}] {}".format(self.entities[str(entity_id)].info.team, err))

	def end_instance_check(self, entity_id, controller):
		self.entities[str(entity_id)].info, self.entities[str(entity_id)].cooldown, actions = controller.get_actions()  # 更新本地实体状态
		local_info = self.entities[str(entity_id)].info
		for action in actions:
			if action[0] == "create":  # 创造新的实体，参数为(type, dir, energy)
				self.add_entity(action[1][0], action[1][2], local_info.location.add(action[1][1]), local_info.team, local_info.ID)
			elif action[0] == "charge":  # 充能，参数为 energy
				self.charge_list.append((entity_id, action[1]))  # 保存id，等到回合结束后比较
			elif action[0] == "overdrive":  # 过载，参数为 radius
				self.available_entities_ids.remove(entity_id)  # 过载后删除本实体
				targets = []
				for rid in self.available_entities_ids:  # 选出所有在半径内的实体
					if self.entities[str(rid)].info.location.distance_to(local_info.location) <= action[1]:
						targets.append(rid)
				
				base_energy = local_info.energy / len(targets)  # 均分能量
				odfactor = self.get_overdrive_factor(local_info.team)  # 获得当前增益系数
				for rid in targets:  # 依次处理
					entity_info = self.entities[str(rid)].info
					if entity_info.team.tag == local_info.team.tag:  # 友军的场合
						if entity_info.type.type == "planet":
							self.entities[str(rid)].info.energy += int(base_energy)
							self.entities[str(rid)].info.defence += int(base_energy)  # 星球同步防护值
						else:
							self.entities[str(rid)].info.defence += int(base_energy * odfactor)
							self.entities[str(rid)].info.defence = min(self.entities[str(rid)].info.defence, self.entities[str(rid)].info.init_defence)  # 限制上限
					else:  # 非友军的场合
						self.entities[str(rid)].info.defence -= int(base_energy * odfactor)
						if entity_info.type.type == "planet":
							if self.entities[str(rid)].info.defence < 0:  # 如果防护值小于零
								self.entities[str(rid)].info.defence = -self.entities[str(rid)].info.defence  # 新实体防护值等于绝对值
								self.entities[str(rid)].info.team = entity_info.team  # 转换队伍
							self.entities[str(rid)].info.energy = self.entities[str(rid)].info.defence  # 星球同步资源点
						elif entity_info.type.type == "destroyer":
							if self.entities[str(rid)].info.defence < 0:  # 如果防护值小于零
								self.entities[str(rid)].info.defence = -self.entities[str(rid)].info.defence  # 新实体防护值等于绝对值
								self.entities[str(rid)].info.defence = min(self.entities[str(rid)].info.defence, self.entities[str(rid)].info.init_defence)  # 限制上限
								self.entities[str(rid)].info.team = local_info.team  # 转换队伍
						else:
							if self.entities[str(rid)].info.defence < 0:  # 如果防护值小于零
								self.available_entities_ids.remove(entity_info.ID)  # 删除实体

			elif action[0] == "analyze":  # 分析，参数为 target
				if action[1].info.type.type == "miner":
					self.available_entities_ids.remove(action[1].info.ID)  # 删除实体
					self.overdrive_factor.append((action[1].info.team.tag, action[1].info.energy, self.round + 50))  # 增加增益

		if local_info.type.type == "miner":  # 开采舰的场合
			if self.round >= self.entities[entity_id].created_round + 50:  # 如果已经超过了50回合
				if self.entities[self.entities[entity_id].created_planet].info.team.tag == local_info.team.tag:  # 如果母星仍然属于本队
					self.entities[self.entities[entity_id].created_planet].info.energy += math.floor((0.02 + 0.03 * math.e ** (-0.001 * self.round)) * self.round)  # 增加资源
					self.entities[self.entities[entity_id].created_planet].info.defence = self.entities[self.entities[entity_id].created_planet].info.energy  # 更新同步防护

	def end_round_check(self):  # 处理开采舰是否进化、计算充能，判断游戏是否结束。
		alive_team = []
		for rid in self.available_entities_ids:
			entity = self.entities[str(rid)]  # 遍历剩余实体
			if entity.info.team.tag not in alive_team:  # 获得还有实体在场的队伍Tag
				alive_team.append(entity.info.team.tag)
			if entity.info.type.type == "miner":  # 判断进化
				if self.round >= entity.created_round + 300:
					self.entities[str(rid)].info.type = EntityType("destroyer")

		if len(alive_team) <= 1:
			self.end_game("eliminate", alive_team[0])  # 结束游戏

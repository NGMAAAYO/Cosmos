import importlib
import random
import json

from core.api import *
from core.entity import Entity

# 定义比赛示例的类
class Instance:
	def __init__(self, teams, map_path, game_round):
		self.team_instances = []
		for team in teams:  # 导入玩家的代码
			self.team_instances.append(importlib.import_module(f"src.{team}.main"))

		self.init_map(map_path)  # 初始化地图
		self.game_round = game_round

		self.round = 0
		self.entities = {}  # 所有的实体
		self.available_entities_ids = []  # 还在场上的实体的ID

	def init_map(self, map_path):
		f = open(map_path, "r", encoding="utf-8")
		fmap = json.loads(f.read())  # 读取json格式的地图
		f.close()

		self.map = fmap["map"]  # 获得地图信息
		for planet in fmap["planets"]:  # 生成初始星球实体
			self.add_entity(EntityType("planet"), planet["energy"], MapLocation(planet["x"], planet["y"]), planet["team"])

	def add_entity(self, entity_type, energy, location, team):
		rid = random.randint(10000, 99999)
		while rid in list(self.entities.keys()):  # 生成唯一ID
			rid = random.randint(10000, 99999)

		self.entities[str(rid)] = Entity(entity_type, energy, location, team, rid) # 添加新的实体
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
			player = self.team_instances[int(entity.info.team)]()  # 实例化玩家的代码
			all_entities = []
			for rid in self.available_entities_ids:  # 获取当前的在场实体
				if rid != entity_id:  # 省略自己
					all_entities.append(self.entities[str(rid)])

			controller = entity.get_controller(all_entities, self.map, self.round, self.overdrive_factor)  # 获取控制器，传给玩家实例
			controller = player.run(controller)  # 运行玩家代码
			self.end_instance_check(entity_id, controller)  # 玩家行动后进行检查，更新全局与本地实体状态
		except Exception as err:
			print("[Team {}] {}".format(entity.info.team, err))
	
	def end_instance_check(self, entity_id, controller):
		self.entities[str(entity_id)].info, self.entities[str(entity_id)].cooldown, actions = controller.get_actions() # 更新本地实体状态
		local_info = self.entities[str(entity_id)].info
		for action in actions:
			if action[0] == "create":  # 创造新的实体，参数为(type, dir, energy)
				self.add_entity(action[1][0], action[1][2], local_info.location.add(action[1][1]), local_info.team)
			elif action[0] == "charge":  # 充能，参数为 energy
				self.charge_list.append((entity_id, action[1]))  # 保存id，等到回合结束后比较
			elif action[0] == "overdrive":  # 过载，参数为 radius
				targets = []
				for rid in self.available_entities_ids:  # 选出所有在半径内的实体
					if self.entities[str(rid)].info.location.distance_to(local_info.location) <= action[1] and rid != entity_id:
						targets.append(rid)
				
				for rid in targets:  # 依次处理
					if self.entities[str(rid)].info.team.tag == local_info.team.tag:  # 友军的场合
						pass

			elif action[0] == "analyze":
				pass

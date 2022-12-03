import math
import copy

from core.api import *


# 实体控制类。记录要产生的行为，并通过get_action函数回调。
class Controller:
	def __init__(self, info, sensed_entities, detected_entities, teams_info, charge_point, gmap, cooldown, round_count, overdrive_factor):
		self.__info = info  # 传入的信息。应当在控制后更新到全局
		self.__cooldown = cooldown  # 传入的冷却信息。应当在控制后更新到全局
		self.__sensed_entities = sensed_entities  # 感知到的实体
		self.__detected_entities = detected_entities  # 探测到的实体（只有位置信息）
		self.__teams_info = teams_info  # 所有队伍的集合
		self.__charge_point = charge_point  # 本队的充能点
		self.__map = gmap  # 地图信息
		self.__round_count = round_count  # 当前的轮数
		self.__overdrive_factor = overdrive_factor  # 全局的过载倍率，每一项为[队伍tag，能量，过期轮数]

		# 以下为回调所调用的数据
		self.__charged = 0  # 用以充能的点数
		self.__to_create = False  # 是否要建造
		self.__create_param = None  # 建造的参数
		self.__to_overdrive = False  # 是否要过载
		self.__overdrive_range = 0  # 过载范围
		self.__to_analyze = False  # 是否要分析
		self.__analyze_target = None  # 分析的目标

	# 根据传入的实体信息检索指定位置的实体的详细信息
	def __search_by_loc(self, loc):
		for info in self.__sensed_entities:
			if info.location.equals(loc):
				return info
		return None

	# 根据传入的实体信息检索指定ID的实体的详细信息
	def __search_by_id(self, rid):
		for info in self.__sensed_entities:
			if info.ID == rid:
				return info
		return None

	# 获得在现在位置执行动作所需要的冷却
	def __get_cooldown(self, base_cooldown):
		return base_cooldown / self.sense_aether(self.__info.location)

	def get_all_teams(self):
		return self.__teams_info

	def get_opponent(self):
		team_list = []
		for t in self.__teams_info:
			if t.tag != self.get_team().tag:
				team_list.append(t)
		return team_list

	def get_cooldown_turns(self):
		return int(self.__cooldown)

	# 计算过载系数
	def get_overdrive_factor(self, team):
		index = 0
		for i in self.__overdrive_factor:
			if i[0] == team.tag and i[2] > self.get_round_num():  # 如果是同一队并且过期轮数大于当前轮数，则累加
				index += i[1]
		return (1.0 + 0.001) ** index

	def get_defence(self):
		return self.__info.defence

	def get_id(self):
		return self.__info.ID

	def get_energy(self):
		return self.__info.energy

	def get_location(self):
		return self.__info.location

	def get_round_num(self):
		return self.__round_count

	def get_team(self):
		return self.__info.team

	def get_type(self):
		return self.__info.type
	
	def get_radio(self):
		return self.__info.radio
	
	# 本队已有的充能点
	def get_charge_point(self):
		return self.__charge_point

	# 指定方向的相邻位置
	def adjacent_location(self, d):
		return self.get_location().add(d)

	def is_opponent(self, team):
		return team.tag in [t.tag for t in self.get_opponent()]

	# 检查指定方向是否被阻挡
	def is_blocked(self, d):
		return self.__search_by_loc(self.adjacent_location(d)) is not None

	# 检查目标位置是否被占用
	def is_location_occupied(self, loc):
		if self.get_location().distance_to(loc) > self.get_type().detection_radius:
			raise Exception("超出探测范围。")
		elif not self.on_the_map(loc):
			raise Exception("指定位置不在地图上。")
		for entity in self.__detected_entities:
			if loc.equals(entity):
				return True
		return False

	# 检查自己是否可以执行动作
	def is_ready(self):
		return self.__cooldown < 1

	# 检查目标位置是否在地图上
	def on_the_map(self, loc):
		if self.get_location().distance_to(loc) > self.get_type().detection_radius:
			raise Exception("超出探测范围。")
		return self.__map.include(loc.x, loc.y)

	# 是否可以探测指定位置
	def can_detect_location(self, loc):
		return self.get_location().distance_to(loc) <= self.get_type().detection_radius and self.on_the_map(loc)

	# 是否可以探测指定半径
	def can_detect_radius(self, radius):
		return radius <= self.get_type().detection_radius

	# 是否可以感知指定位置
	def can_sense_location(self, loc):
		if self.get_location().distance_to(loc) <= self.get_type().sensor_radius:
			if self.on_the_map(loc):
				return True
		return False

	# 是否可以感知指定半径
	def can_sense_radius(self, radius):
		return self.get_type().sensor_radius >= radius

	# 感知符合条件的实体
	def sense_entity(self, arg):
		if isinstance(arg, int):
			return self.__search_by_id(arg)
		elif isinstance(arg, MapLocation):
			return self.__search_by_loc(arg)

	# 感知指定范围内符合条件的实体
	def sense_nearby_entities(self, center=None, radius=None, teams=None):
		if center is None:
			center = self.get_location()
		if radius is None:
			radius = self.get_type().sensor_radius
		entities = []
		for entity in self.__sensed_entities:
			if entity.location.distance_to(center) <= radius:
				if teams is None or entity.team.tag in [t.tag for t in teams]:
					entities.append(entity)
		return entities

	# 探测一定范围内所有的实体
	def detect_nearby_entities(self, radius):
		loc = []
		for entity in self.__detected_entities:
			if entity.distance_to(self.get_location()) <= radius:
				loc.append(entity)
		return loc

	# 感知指定位置的以太密度
	def sense_aether(self, loc):
		if loc.distance_to(self.get_location()) > self.get_type().sensor_radius:
			raise Exception("超出感知范围。")
		if not self.on_the_map(loc):
			raise Exception("目标不在地图上。")
		return self.__map.get_aether(loc.x, loc.y)

	# 是否有多少能量
	def can_charge(self, energy):
		return self.get_type().name == "planet" and self.get_energy() >= energy

	# 是否可以以指定的参数建造
	def can_build(self, entity_type, d, energy):
		energy = int(energy)
		return self.get_type().name == "planet" and entity_type.name != "planet" and not self.is_blocked(d) and self.get_energy() >= energy > 0 and self.is_ready()

	# 是否可以在指定半径过载
	def can_overdrive(self, radius):
		return self.get_type().name == "destroyer" and radius <= self.get_type().action_radius and self.is_ready()

	# 是否可以分析指定的ID或者指定的位置
	def can_analyze(self, arg):
		if self.get_type().name == "scout" and self.is_ready():
			target = None
			if isinstance(arg, int):
				target = self.__search_by_id(arg)
			elif isinstance(arg, MapLocation):
				target = self.__search_by_loc(arg)
			if target is not None:
				if target.location.distance_to(self.get_location()) <= self.get_type().action_radius:  # 检测到并且在作用范围之内
					return True
		return False

	# 是否可以向指定方向移动
	def can_move(self, d):
		return self.is_ready() and not self.is_blocked(d) and self.on_the_map(self.adjacent_location(d))

	# 是否可以改为指定广播值
	@staticmethod
	def can_set_radio(radio):
		return 0 <= radio <= 99999999

	# 尝试充能
	def charge(self, energy):
		energy = int(energy)
		if self.get_type().name != "planet":
			raise Exception("只有星球可以充能。")
		elif self.get_energy() < energy:
			raise Exception("能量不足。")
		elif energy <= 0:
			raise Exception("能量必须为正整数。")
		else:
			self.__info.energy -= energy
			self.__charged = energy

	# 尝试建造
	def build(self, entity_type, d, energy):
		energy = int(energy)
		if self.get_type().name != "planet":
			raise Exception("只有星球可以建造。")
		elif entity_type.name == "planet":
			raise Exception("星球无法被建造。")
		elif self.__search_by_loc(self.adjacent_location(d)) is not None:
			raise Exception("目标位置被阻塞。")
		elif self.__info.energy < energy:
			raise Exception("能量不足。")
		elif energy <= 0:
			raise Exception("能量必须为正整数。")
		elif not self.is_ready():
			raise Exception("冷却值必须小于 1。")
		else:
			self.__info.energy -= energy
			self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)
			self.__to_create = True
			self.__create_param = [entity_type, d, energy]

	# 尝试过载
	def overdrive(self, radius):
		if self.get_type().name != "destroyer":
			raise Exception("只有战列舰可以过载。")
		if not self.can_overdrive(radius):
			raise Exception("无法以指定的参数过载。")
		elif not self.is_ready():
			raise Exception("冷却值必须小于 1。")
		else:
			self.__to_overdrive = True
			self.__overdrive_range = radius
			self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)

	# 尝试分析
	def analyze(self, arg):
		if self.get_type().name != "scout":
			raise Exception("只有侦查舰可以分析。")
		if not self.can_analyze(arg):
			raise Exception("无法以指定的参数分析。")
		elif not self.is_ready():
			raise Exception("冷却值必须小于 1。")

		target = None
		if isinstance(arg, int):
			target = self.__search_by_id(arg)
		elif isinstance(arg, MapLocation):
			target = self.__search_by_loc(arg)
		self.__to_analyze = True
		self.__analyze_target = target
		self.__info.defence = max(self.__info.defence - 10, 0)
		self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)

	# 尝试移动
	def move(self, d):
		if not self.is_ready():
			raise Exception("冷却值必须小于 1。")
		elif self.is_blocked(d):
			raise Exception("目标位置被阻塞。")
		elif self.get_type().name == "planet":
			raise Exception("星球无法移动。")
		elif not self.on_the_map(self.adjacent_location(d)):
			raise Exception("目标位置不在地图上。")
		else:
			self.__info.location = self.adjacent_location(d)  # 直接更新
			self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)

	# 尝试设置广播内容
	def set_radio(self, radio):
		if not self.can_set_radio(radio):
			raise Exception("广播值超出范围。")
		else:
			self.__info.radio = radio

	# 回调动作
	def get_actions(self):
		actions = []
		if self.get_type().name == "planet":
			if self.__to_create:
				actions.append(["create", self.__create_param])
			actions.append(["charge", self.__charged])
			self.__info.defence = self.__info.energy  # 星球的防护值与能量同步

		elif self.get_type().name == "destroyer":
			if self.__to_overdrive:
				actions.append(["overdrive", self.__overdrive_range])

		elif self.get_type().name == "scout":
			if self.__to_analyze:
				actions.append(["analyze", self.__analyze_target])

		return self.__info, self.__cooldown, actions  # 所有需要更新的信息


# 实体包装类
class Entity:
	def __init__(self, rtype, energy, location, team, cround, cplanet, rid):
		self.info = EntityInfo(math.ceil(energy * rtype.defence_ratio), rid, energy, location, team, rtype, 0)
		self.cooldown = rtype.initial_cooldown
		self.created_round = cround
		self.created_planet = cplanet  # 创造此实体的星球的ID
	
	def get_controller(self, all_entities, teams_info, charge_result, gmap, round_count, overdrive_factor):
		sensed_entities = []
		detected_entities = []
		for entity in all_entities:  # 获得实体能感知和探测到的所有实体
			d = entity.location.distance_to(self.info.location)
			if d <= self.info.type.detection_radius:
				detected_entities.append(entity.location)
				if d <= self.info.type.sensor_radius:
					if self.info.type.name in ["destroyer", "miner"] and entity.type.name == "miner" and entity.ID != self.info.ID:  # 非真实视野
						new_entity = copy.deepcopy(entity)
						new_entity.type = EntityType("destroyer")
						sensed_entities.append(new_entity)
					else:
						sensed_entities.append(entity)

		return Controller(self.info, sensed_entities, detected_entities, teams_info, charge_result[int(self.info.team.tag)], gmap, self.cooldown, round_count, overdrive_factor)

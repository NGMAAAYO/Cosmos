from api import *

# 实体控制类。记录要产生的行为，并通过get_action函数回调。
class Controller:
	def __init__(self, info, sensed_entities, detected_entities, aether, cooldown, round_count, overdrive_factor):
		self.__info = info  # 传入的信息。应当在控制后更新到全局
		self.__cooldown = cooldown  # 传入的冷却信息。应当在控制后更新到全局
		self.__sensed_entities = sensed_entities  # 感知到的实体
		self.__detected_entities = detected_entities  # 探测到的实体（只有位置信息）
		self.__aether = aether  # 附近的以太密度
		self.__round_count = round_count # 当前的轮数
		self.__overdrive_factor = overdrive_factor  # 全局的过载倍率

		# 以下为回调所调用的数据
		self.__charged = 0  # 用以充能的点数
		self.__tocreate = False  # 是否要建造
		self.__create_param = None  # 建造的参数
		self.__tooverdrive = False # 是否要过载
		self.__overdrive_range = 0 # 过载范围
		self.__toanalyze = False # 是否要分析
		self.__analyze_target = None # 分析的目标
		self.__tomove = False # 是否要移动
		self.__move_direction = None # 移动的方向
		self.__to_set_radio = True # 是否要设置广播
		self.__set_radio = 0  # 设置的参数

	# 根据传入的实体信息检索指定位置的实体的详细信息
	def __search_by_loc(self, loc):
		for info in self.__sensed_entities:
			if info.location.equals(loc):
				return info
		return None

	# 根据传入的实体信息检索指定ID的实体的详细信息
	def __search_by_ID(self, rid):
		for info in self.__sensed_entities:
			if info.ID == rid:
				return info
		return None

	# 获得在现在位置执行动作所需要的冷却
	def __get_cooldown(self, base_cooldown):
		return base_cooldown / self.sense_aether(self.__info.location)

	def get_cooldown_turns(self):
		return int(self.__cooldown)

	def get_overdrive_factor(self, team):
		index = 0
		for i in self.__overdrive_factor:
			if i[0] == team.tag and i[2] <= self.get_round_num():
				index += i[1]
		return 1.0 + 0.001 * index

	def get_defence(self):
		return self.__info.defence

	def get_ID(self):
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

	# 指定方向的相邻位置
	def adjacent_location(self, d):
		return self.__info.location.add(d)

	# 检查指定方向是否被阻挡
	def is_blocked(self, d):
		return self.__search_by_loc(self.adjacent_location(d)) != None

	# 检查目标位置是否被占用
	def is_location_occupied(self, loc):
		if not self.can_detect_location(loc):
			raise Exception("超出探测范围。")
		for entity in self.__detected_entities:
			if loc.equals(entity.location):
				return True
		return False

	# 检查自己是否可以执行动作
	def is_ready(self):
		if self.__cooldown < 1:
			return True
		return False

	# 检查目标位置是否在地图上
	def on_the_map(self, loc):
		if not self.can_sense_location(loc):
			raise Exception("超出探测范围。")
		for p in self.__aether:
			if p[0] == loc.x and p[1] == loc.y:
				return True
		return False

	# 是否可以探测指定位置
	def can_detect_location(self, loc):
		return self.__info.location.distance_to(loc) <= self.__info.type.detection_radius

	# 是否可以探测指定半径
	def can_detect_radius(self, radius):
		return radius <= self.__info.type.detection_radius

	# 是否可以感知指定位置
	def can_sense_location(self, loc):
		return self.__info.location.distance_to(loc) <= self.__info.type.sensor_radius

	# 是否可以感知指定半径
	def can_sense_radius(self, radius):
		return self.__info.type.sensor_radius >= radius

	# 感知符合条件的实体
	def sense_entity(self, arg):
		if isinstance(arg, int):
			return self.__search_by_ID(arg)
		elif isinstance(arg, MapLocation):
			return self.__search_by_loc(arg)

	# 感知指定范围内符合条件的实体
	def sense_nearby_entities(self, center=None, radius=None, team=None):
		if center == None:
			center = self.get_location()
		if radius == None:
			radius = self.__info.type.sensor_radius
		entities = []
		for entity in self.__sensed_entities:
			if entity.location.distance_to(center) <= radius:
				if team == None or entity.team.tag == team.tag:
					entities.append(entity)
		return entities

	# 探测一定范围内所有的实体
	def detect_nearby_entities(self, radius):
		locs = []
		for entity in self.__detected_entities:
			if entity.location.distance_to(self.__info.location) <= radius:
				locs.append(entity.location)
		return locs

	# 感知指定位置的以太密度
	def sense_aether(self, loc):
		if loc.distance_to(self.__info.location) > self.__info.type.detection_radius:
			raise Exception("超出探测范围。")
		for p in self.__aether:
			if p[0] == loc.x and p[1] == loc.y:
				return p[2]
		raise Exception("目标不在地图上。")

	# 是否有多少能量
	def can_charge(self, energy):
		if self.__info.energy >= energy:
			return True
		return False

	# 是否可以以指定的参数建造
	def can_build(self, entity_type, d, energy):
		energy = int(energy)
		return entity_type.type != "planet" and not self.is_blocked(d) and self.can_charge(energy) and energy > 0 and self.is_ready()

	# 是否可以在指定半径过载
	def can_overdrive(self, radius):
		return self.__info.type == "destroyer" and radius <= self.__info.type.action_radius and self.is_ready()

	# 是否可以分析指定的ID或者指定的位置
	def can_analyze(self, arg):
		if not self.is_ready():  # 检查冷却
			return False
		elif self.__info.type != "scout":
			return False
		target = None
		if isinstance(arg, int):
			target = self.__search_by_ID(arg)
		elif isinstance(arg, MapLocation):
			target = self.__search_by_loc(arg)
		if target != None:
			if target.location.distance_to(self.__info.location) <= self.__info.type.action_radius:  # 检测到并且在作用范围之内
				return True
		return False

	# 是否可以向指定方向移动
	def can_move(self, d):
		return self.is_ready() and not self.is_blocked(d)

	# 是否可以改为指定广播值
	def can_set_radio(self, radio):
		return radio >= 0 and radio <= 99999999

	# 尝试充能
	def charge(self, energy):
		energy = int(energy)
		if self.__info.type.type != "planet":
			raise Exception("只有星球可以充能。")
		elif self.__info.energy < energy:
			raise Exception("能量不足。")
		elif energy <= 0:
			raise Exception("能量必须为正整数。")
		else:
			self.__info.energy -= energy
			self.__charged = energy

	# 尝试建造
	def build_entity(self, entity_type, d, energy):
		energy = int(energy)
		if entity_type.type == "planet":
			raise Exception("星球无法被建造。")
		elif self.__search_by_loc(self.adjacent_location(d)) != None:
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
			self.__tocreate = True
			self.__create_param = [entity_type, d, energy]
		return

	# 尝试过载
	def overdrive(self, radius):
		if self.can_overdrive(radius):
			raise Exception("无法以指定的参数过载。")
		elif not self.is_ready():
			raise Exception("冷却值必须小于 1。")
		else:
			self.__tooverdrive = True
			self.__overdrive_range = radius
			self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)

	# 尝试分析
	def analyze(self, arg):
		if not self.can_analyze(arg):
			raise Exception("无法以指定的参数分析。")
		elif not self.is_ready():
			raise Exception("冷却值必须小于 1。")

		target = None
		if isinstance(arg, int):
			target = self.__search_by_ID(arg)
		elif isinstance(arg, MapLocation):
			target = self.__search_by_loc(arg)
		self.__toanalyze = True
		self.__analyze_target = target
		self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)

	# 尝试移动
	def move(self, d):
		if not self.is_ready():
			raise Exception("冷却值必须小于 1。")
		elif self.is_blocked(d):
			raise Exception("目标位置被阻塞。")
		elif not self.on_the_map(self.adjacent_location(d)):
			raise Exception("目标位置不在地图上。")
		else:
			self.__tomove = True
			self.__move_direction = d
			self.__cooldown += self.__get_cooldown(self.__info.type.action_cooldown)

	# 尝试设置广播内容
	def set_radio(self, radio):
		if not self.can_set_radio(radio):
			raise Exception("广播超出范围。")
		else:
			self.__to_set_radio = True
			self.__set_radio = radio

	# 回调动作
	def get_actions(self):
		actions = []
		if self.__info.type.type == "planet":
			if self.__tocreate:
				actions.append(["create", self.__create_param])
			actions.append(["charge", self.__charged])

		elif self.__info.type.type == "destroyer":
			if self.__tooverdrive:
				actions.append(["overdrive", self.__overdrive_range])

		elif self.__info.type.type == "scout":
			if self.__toanalyze:
				actions.append(["analyze", self.__analyze_target])

		if self.__info.type.type != "planet":
			if self.__tomove:
				self.__info.location = self.get_location().add(self.__move_direction)  # 直接更新

		if self.__to_set_radio:
			self.__info.radio = self.__set_radio  # 直接更新

		return self.__info, self.__cooldown, actions  # 所有需要更新的信息


class Entity:
	def __init__(self, rtype, energy, location, team, rid):
		self.info = EntityInfo(energy*rtype.defence_ratio, rid, energy, location, team, rtype, 0)
		self.cooldown = rtype.initial_cooldown
	
	def get_controller(self, all_entities, map, round_count, overdrive_factor):
		sensed_entities = []
		detected_entities = []
		aether = []
		for entity in all_entities:  # 获得实体能感知和探测到的所有实体
			d = entity.info.location.distance_to(self.info.location)
			if d <= self.info.type.detection_radius:
				detected_entities.append(entity.info.location)
				if d <= self.info.type.sensor_radius:
					sensed_entities.append(entity.info)

		for i in range(len(map)):
			for j in range(len(map[0])):
				if MapLocation(i, j).distance_to(self.info.location) <= self.info.type.sensor_radius:  # i和j的顺序存疑，需要debug
					aether.append(map[i][j])

		return Controller(self.info, sensed_entities, detected_entities, aether, self.cooldown, round_count, overdrive_factor)
# 方向的基本类
class Direction:
	def __init__(self, dx=0, dy=0):
		self.dx = dx
		self.dy = dy

	def __repr__(self):
		names = [["south_west", "west", "north_west"], ["south", "center", "north"], ["south_east", "east", "north_east"]]
		return str(names[self.dx + 1][self.dy + 1])

	def __str__(self):
		names = [["south_west", "west", "north_west"], ["south", "center", "north"], ["south_east", "east", "north_east"]]
		return str(names[self.dx + 1][self.dy + 1])

	def __eq__(self, d):
		return self.equals(d)

	@staticmethod
	def center():
		return Direction(0, 0)

	@staticmethod
	def north():
		return Direction(0, 1)

	@staticmethod
	def north_east():
		return Direction(1, 1)

	@staticmethod
	def east():
		return Direction(1, 0)

	@staticmethod
	def south_east():
		return Direction(1, -1)

	@staticmethod
	def south():
		return Direction(0, -1)

	@staticmethod
	def south_west():
		return Direction(-1, -1)

	@staticmethod
	def west():
		return Direction(-1, 0)

	@staticmethod
	def north_west():
		return Direction(-1, 1)

	@staticmethod
	def all_directions():
		dirs = []
		for i in [0, -1, 1]:
			for j in [0, -1, 1]:
				dirs.append(Direction(i, j))
		return dirs

	@staticmethod
	def cardinal_directions():
		return [Direction.north(), Direction.south(), Direction.east(), Direction.west()]

	def get_dx(self):
		return self.dx

	def get_dy(self):
		return self.dy

	def opposite(self):
		return Direction(-self.dx, -self.dy)

	def rotate_left(self):
		if self.dx == 0 and self.dy == 0:
			return self.center()
		_ordered_dirs = [
			self.east(), self.north_east(), self.north(), self.north_west(),
			self.west(), self.south_west(), self.south(), self.south_east()
		]
		return _ordered_dirs[(_ordered_dirs.index(self) + 1) % 8]

	def rotate_right(self):
		if self.dx == 0 and self.dy == 0:
			return self.center()
		_ordered_dirs = [
			self.east(), self.north_east(), self.north(), self.north_west(),
			self.west(), self.south_west(), self.south(), self.south_east()
		]
		return _ordered_dirs[(_ordered_dirs.index(self) - 1) % 8]

	def equals(self, d):
		if isinstance(d, Direction) and self.dx == d.dx and self.dy == d.dy:
			return True
		return False


# 地图位置的基本类
class MapLocation:
	def __init__(self, x=0, y=0):
		self.x = x
		self.y = y

	def __repr__(self):
		return str((self.x, self.y))

	def __str__(self):
		return str((self.x, self.y))

	def __eq__(self, loc):
		return self.equals(loc)

	def add(self, d):
		return MapLocation(self.x + d.dx, self.y + d.dy)

	# 获得到达目标位置的最近方向
	def direction_to(self, loc):
		dx = loc.x - self.x
		dy = loc.y - self.y
		if dx > 0:
			dx = 1
		if dx < 0:
			dx = -1
		if dy > 0:
			dy = 1
		if dy < 0:
			dy = -1
		return Direction(dx, dy)

	# 与某个位置的欧几里得距离
	def distance_to(self, loc):
		return (loc.x - self.x) ** 2 + (loc.y - self.y) ** 2

	# 是否与某个位置相邻
	def is_adjacent_to(self, loc):
		return abs(self.x - loc.x) <= 1 and abs(self.y - loc.y) <= 1

	def subtract(self, d):
		return MapLocation(self.x - d.dx, self.y - d.dy)

	def translate(self, dx, dy):
		return MapLocation(self.x + dx, self.y + dy)

	def equals(self, loc):
		return self.x == loc.x and self.y == loc.y
		
	def to_tuple(self):
		return self.x, self.y


# 实体类型的基本类
class EntityType:
	def __repr__(self):
		return self.name

	def __str__(self):
		return self.name

	def __eq__(self, etype):
		if isinstance(etype, EntityType):
			return self.name == etype.name
		elif isinstance(etype, str):
			return self.name == etype
		return False

	def __init__(self, entity_type):
		if entity_type == "destroyer":
			self.name = entity_type
			self.action_cooldown = 1.0
			self.action_radius = 9
			self.defence_ratio = 1.0
			self.detection_radius = 25
			self.initial_cooldown = 10
			self.sensor_radius = 25
		elif entity_type == "miner":
			self.name = entity_type
			self.action_cooldown = 2.0
			self.action_radius = 0
			self.defence_ratio = 1.0
			self.detection_radius = 20
			self.initial_cooldown = 0
			self.sensor_radius = 20
		elif entity_type == "scout":
			self.name = entity_type
			self.action_cooldown = 1.5
			self.action_radius = 12
			self.defence_ratio = 0.7
			self.detection_radius = 40
			self.initial_cooldown = 10
			self.sensor_radius = 30
		elif entity_type == "planet":
			self.name = entity_type
			self.action_cooldown = 2.0
			self.action_radius = 2
			self.defence_ratio = 1.0
			self.detection_radius = 40
			self.initial_cooldown = 0
			self.sensor_radius = 40
		else:
			raise Exception("无效的种类。")

	@staticmethod
	def all_types():
		return [EntityType("destroyer"), EntityType("miner"), EntityType("scout"), EntityType("planet")]


# 实体信息的基本类
class EntityInfo:
	def __init__(self, defence, rid, energy, location, team, rtype, radio):
		self.energy = energy  # 能量值
		self.defence = defence if rtype.name != "planet" else self.energy  # 防护值
		self.init_defence = defence  # 初始防护值
		self.ID = rid  # 独有ID
		self.location = location  # 当前位置
		self.team = team  # 所属队伍
		self.type = rtype  # 实体种类
		self.radio = radio  # 广播值

	def copy(self):
		return EntityInfo(self.defence, self.ID, self.energy, self.location, self.team, self.type, self.radio)

	def to_dict(self):
		return {"ID": self.ID, "energy": self.energy, "defence": self.defence, "location": self.location.to_tuple(), "team": self.team.tag, "type": self.type.name, "radio": self.radio}


class Team:
	def __repr__(self):
		return self.tag

	def __str__(self):
		return self.tag

	def __eq__(self, team):
		if isinstance(team, Team):
			return self.tag == team.tag
		elif isinstance(team, str):
			return self.tag == team
		return False

	def __init__(self, team):
		self.tag = str(team)

	def is_player(self):
		return self.tag != "Neutral"

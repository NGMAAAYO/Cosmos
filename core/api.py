from __future__ import annotations
from typing import List, Tuple, Union

# 方向的基本类
class Direction:
	def __init__(self, dx: int = 0, dy: int = 0) -> None:
		self.dx = dx
		self.dy = dy

	def __repr__(self) -> str:
		names = [["south_west", "west", "north_west"], ["south", "center", "north"], ["south_east", "east", "north_east"]]
		return str(names[self.dx + 1][self.dy + 1])

	def __str__(self) -> str:
		names = [["south_west", "west", "north_west"], ["south", "center", "north"], ["south_east", "east", "north_east"]]
		return str(names[self.dx + 1][self.dy + 1])

	def __eq__(self, d: object) -> bool:
		if isinstance(d, Direction):
			return self.equals(d)
		return False

	@staticmethod
	def center() -> Direction:
		return Direction(0, 0)

	@staticmethod
	def north() -> Direction:
		return Direction(0, 1)

	@staticmethod
	def north_east() -> Direction:
		return Direction(1, 1)

	@staticmethod
	def east() -> Direction:
		return Direction(1, 0)

	@staticmethod
	def south_east() -> Direction:
		return Direction(1, -1)

	@staticmethod
	def south() -> Direction:
		return Direction(0, -1)

	@staticmethod
	def south_west() -> Direction:
		return Direction(-1, -1)

	@staticmethod
	def west() -> Direction:
		return Direction(-1, 0)

	@staticmethod
	def north_west() -> Direction:
		return Direction(-1, 1)

	@staticmethod
	def all_directions() -> List[Direction]:
		dirs = []
		for i in [0, -1, 1]:
			for j in [0, -1, 1]:
				dirs.append(Direction(i, j))
		return dirs

	@staticmethod
	def cardinal_directions() -> List[Direction]:
		return [Direction.north(), Direction.south(), Direction.east(), Direction.west()]

	def get_dx(self) -> int:
		return self.dx

	def get_dy(self) -> int:
		return self.dy

	def opposite(self) -> Direction:
		return Direction(-self.dx, -self.dy)

	def rotate_left(self) -> Direction:
		if self.dx == 0 and self.dy == 0:
			return self.center()
		_ordered_dirs = [
			self.east(), self.north_east(), self.north(), self.north_west(),
			self.west(), self.south_west(), self.south(), self.south_east()
		]
		return _ordered_dirs[(_ordered_dirs.index(self) + 1) % 8]

	def rotate_right(self) -> Direction:
		if self.dx == 0 and self.dy == 0:
			return self.center()
		_ordered_dirs = [
			self.east(), self.north_east(), self.north(), self.north_west(),
			self.west(), self.south_west(), self.south(), self.south_east()
		]
		return _ordered_dirs[(_ordered_dirs.index(self) - 1) % 8]

	def equals(self, d: Direction) -> bool:
		return self.dx == d.dx and self.dy == d.dy


# 地图位置的基本类
class MapLocation:
	def __init__(self, x: int = 0, y: int = 0) -> None:
		self.x = x
		self.y = y

	def __repr__(self) -> str:
		return str((self.x, self.y))

	def __str__(self) -> str:
		return str((self.x, self.y))

	def __eq__(self, loc: object) -> bool:
		if isinstance(loc, MapLocation):
			return self.equals(loc)
		return False

	def add(self, d: Direction) -> MapLocation:
		return MapLocation(self.x + d.dx, self.y + d.dy)

	# 获得到达目标位置的最近方向
	def direction_to(self, loc: MapLocation) -> Direction:
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
	def distance_to(self, loc: MapLocation) -> int:
		return (loc.x - self.x) ** 2 + (loc.y - self.y) ** 2

	# 是否与某个位置相邻
	def is_adjacent_to(self, loc: MapLocation) -> bool:
		return abs(self.x - loc.x) <= 1 and abs(self.y - loc.y) <= 1

	def subtract(self, d: Direction) -> MapLocation:
		return MapLocation(self.x - d.dx, self.y - d.dy)

	def translate(self, dx: int, dy: int) -> MapLocation:
		return MapLocation(self.x + dx, self.y + dy)

	def equals(self, loc: MapLocation) -> bool:
		return self.x == loc.x and self.y == loc.y
		
	def to_tuple(self) -> Tuple[int, int]:
		return self.x, self.y


# 实体类型的基本类
class EntityType:
	def __repr__(self) -> str:
		return self.name

	def __str__(self) -> str:
		return self.name

	def __eq__(self, etype: Union[EntityType, str]) -> bool:
		if isinstance(etype, EntityType):
			return self.name == etype.name
		elif isinstance(etype, str):
			return self.name == etype
		return False

	def __init__(self, entity_type: str) -> None:
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
	def all_types() -> List[EntityType]:
		return [EntityType("destroyer"), EntityType("miner"), EntityType("scout"), EntityType("planet")]


# 实体信息的基本类
class EntityInfo:
	def __init__(self, defence: int, rid: int, energy: int, location: MapLocation, team: Team, rtype: EntityType, radio: int) -> None:
		self.energy = energy  # 能量值
		self.defence = defence if rtype.name != "planet" else self.energy  # 防护值
		self.init_defence = defence  # 初始防护值
		self.ID = rid  # 独有ID
		self.location = location  # 当前位置
		self.team = team  # 所属队伍
		self.type = rtype  # 实体种类
		self.radio = radio  # 广播值

	def copy(self) -> EntityInfo:
		return EntityInfo(self.defence, self.ID, self.energy, self.location, self.team, self.type, self.radio)

	def to_dict(self) -> dict:
		return {"ID": self.ID, "energy": self.energy, "defence": self.defence, "location": self.location.to_tuple(), "team": self.team.tag, "type": self.type.name, "radio": self.radio}


class Team:
	def __repr__(self) -> str:
		return self.tag

	def __str__(self) -> str:
		return self.tag

	def __eq__(self, team: Union[Team, str]) -> bool:
		if isinstance(team, Team):
			return self.tag == team.tag
		elif isinstance(team, str):
			return self.tag == team
		return False

	def __init__(self, team: str) -> None:
		self.tag = str(team)

	def is_player(self) -> bool:
		return self.tag != "Neutral"

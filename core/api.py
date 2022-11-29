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

	def center():
		return Direction(0, 0)

	def north():
		return Direction(0, 1)

	def north_east():
		return Direction(1, 1)

	def east():
		return Direction(1, 0)

	def south_east():
		return Direction(1, -1)

	def south():
		return Direction(0, -1)

	def south_west():
		return Direction(-1, -1)

	def west():
		return Direction(-1, 0)

	def north_west():
		return Direction(-1, 1)

	def all_directions():
		dirs = []
		for i in [0, -1, 1]:
			for j in [0, -1, 1]:
				dirs.append(Direction(i, j))
		return dirs

	def cardinal_directions():
		return [Direction.north(), Direction.south(), Direction.east(), Direction.west()]

	def getdx(self):
		return self.dx

	def getdy(self):
		return self.dy

	def opposite(self):
		return Direction(-self.dx, -self.dy)

	def rotate_left(self):
		dirs = [[Direction.south(), Direction.south_west(), Direction.west()], [Direction.south_east(), Direction.center(), Direction.north_west()], [Direction.south(), Direction.north_east(), Direction.north()]]
		return dirs[self.dx + 1][self.dy + 1]

	def rotate_right(self):
		dirs = [[Direction.west(), Direction.north_west(), Direction.north()], [Direction.south_west(), Direction.center(), Direction.north_east()], [Direction.east(), Direction.south_east(), Direction.east()]]
		return dirs[self.dx + 1][self.dy + 1]

	def equals(self, dir):
		if isinstance(dir, Direction) and self.dx == dir.dx and self.dy == dir.dy:
			return True
		return False

class MapLocation:
	def __init__(self, x=0, y=0):
		self.x = x
		self.y = y

	def __repr__(self):
		return str((self.x, self.y))

	def __str__(self):
		return str((self.x, self.y))

	def add(self, d):
		return MapLocation(self.x + d.dx, self.y + d.dy)

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

	def distance_to(self, loc):
		return (loc.x - self.x) ** 2 + (loc.y - self.y) ** 2

	def is_adjacent_to(self, loc):
		return abs(self.x - loc.x) <= 1 and abs(self.y - loc.y) <= 1

	def subtract(self, d):
		return MapLocation(self.x - d.dx, self.y - d.dy)

	def translate(self, dx, dy):
		return MapLocation(self.x + dx, self.y + dy)

	def equals(self, loc):
		return self.x == loc.x and self.y == loc.y

class RobotType:
	def __repr__(self):
		return self.robot_type

	def __str__(self):
		return self.robot_type

	def __init__(self, type):
		if True:
			pass
		else:
			raise Exception("参数有误。")

class RobotInfo:
	def __init__(self, defence, ID, energy, location, team, type):
		self.defence = defence
		self.ID = ID
		self.energy = energy
		self.location = location
		self.team = team
		self.type = type

	def copy(self):
		return RobotInfo(self.defence, self.ID, self.energy, self.location, self.team, self.type)
		

class Team:
	def __repr__(self):
		return self.tag

	def __str__(self):
		return self.tag

	def __init__(self, team):
		if team in ["A", "B", "Neutral"]:
			self.tag = team
		else:
			raise Exception("参数有误。")

	def opponent(self):
		if self.tag == "A":
			return Team("B")
		elif self.tag == "B":
			return Team("A")
		else:
			return None

	def is_player(self):
		return self.tag in ["A", "B"]


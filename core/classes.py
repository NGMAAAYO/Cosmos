# 定义游戏地图的类
class Map:
	def __init__(self, aether_dense, map_size, dx=0, dy=0):
		self.content = []
		self.width = map_size[0]
		self.height = map_size[1]
		self.dx = dx
		self.dy = dy
		for i in range(self.height):
			line = []
			for j in range(self.width):
				for block in aether_dense:
					if block["x"] == i and block["y"] == j:
						line.append(block["aether"])
			self.content.append(line)

	def get_aether(self, x, y):
		return self.content[x-self.dx][y-self.dy]

	def include(self, x, y):
		return (self.dx <= x < self.dx + self.width) and (self.dy <= y < self.dy + self.height)

	def to_dict(self):
		return {"content": self.content, "size": (self.width, self.height), "origin": (self.dx, self.dy)}

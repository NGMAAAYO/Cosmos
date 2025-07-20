from typing import List, Tuple

# 定义游戏地图的类
class Map:
	def __init__(self, aether_dense: List[dict], map_size: Tuple[int, int], dx: int = 0, dy: int = 0) -> None:
		self.content = []
		self.width = map_size[0]
		self.height = map_size[1]
		self.dx = dx
		self.dy = dy
		for i in range(self.width):
			line = []
			for j in range(self.height):
				for block in aether_dense:
					if block["x"] == i and block["y"] == j:
						line.append(block["aether"])
			self.content.append(line)

	def get_aether(self, x: int, y: int) -> float:
		return self.content[x-self.dx][y-self.dy]

	def include(self, x: int, y: int) -> bool:
		return (self.dx <= x < self.dx + self.width) and (self.dy <= y < self.dy + self.height)

	def to_dict(self) -> dict:
		return {"content": self.content, "size": (self.width, self.height), "origin": (self.dx, self.dy)}
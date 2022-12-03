import cv2
import json
import numpy as np
from tqdm import tqdm


class DemoPlayer:
	def __init__(self, block_size=20):
		self.block_size = block_size
		self.default_fps = 4
		self.destroyer_icon = cv2.resize(cv2.imread("./res/destroyer.png"), (self.block_size, self.block_size))
		self.miner_icon = cv2.resize(cv2.imread("./res/miner.png"), (self.block_size, self.block_size))
		self.scout_icon = cv2.resize(cv2.imread("./res/scout.png"), (self.block_size, self.block_size))
		self.planet_icon = cv2.resize(cv2.imread("./res/planet.png"), (self.block_size, self.block_size))
		self.destroyer_icon_mask = self.get_icon_mask(self.destroyer_icon)
		self.miner_icon_mask = self.get_icon_mask(self.miner_icon)
		self.scout_icon_mask = self.get_icon_mask(self.scout_icon)
		self.planet_icon_mask = self.get_icon_mask(self.planet_icon)

		self.replay = None
		self.background = None
		self.frames = []
		self.w = 0
		self.h = 0

	def load(self, demo_path):
		with open(demo_path, "r", encoding="utf-8") as f:
			self.replay = json.loads(f.read())
			self.w = self.replay["map"]["size"][0]
			self.h = self.replay["map"]["size"][1]
			self.background = self.make_background()

	def get_img_index(self, x, y):
		return ((self.h - y - 1) * self.block_size, (self.h - y) * self.block_size), (x * self.block_size, (x + 1) * self.block_size)

	def get_icon_mask(self, icon):
		img = np.ones((self.block_size, self.block_size, 3))
		for i in range(self.block_size):
			for j in range(self.block_size):
				if icon[i, j, :].all() == np.array([0, 0, 0]).all():
					img[i, j, :] *= 0
		return img

	def make_background(self):
		img = np.ones((self.h * self.block_size, self.w * self.block_size, 3))  # h, w, c
		for x in range(self.w):
			for y in range(self.h):
				index = self.get_img_index(x, y)
				img[index[0][0]: index[0][1], index[1][0]:index[1][1], :] *= self.replay["map"]["content"][x][y]
		return img

	@staticmethod
	def colorize(image, bgr=(255, 255, 255)):
		img = image.copy()
		img[:, :, 0] *= bgr[0]
		img[:, :, 1] *= bgr[1]
		img[:, :, 2] *= bgr[2]
		return img

	def make_frame(self, frame_index):
		frame = self.background.copy() / 2
		entities = self.replay["rounds"][frame_index]
		for entity in entities:
			x = entity["location"][0] - self.replay["map"]["origin"][0]
			y = entity["location"][1] - self.replay["map"]["origin"][1]
			index = self.get_img_index(x, y)
			color = [(200, 200, 255), (255, 200, 200)][int(entity["team"])]
			icon = mask = None
			if entity["type"] == "planet":
				icon = self.colorize(self.planet_icon, color)
				mask = self.planet_icon_mask
			elif entity["type"] == "destroyer":
				icon = self.colorize(self.destroyer_icon, color)
				mask = self.destroyer_icon_mask
			elif entity["type"] == "miner":
				icon = self.colorize(self.miner_icon, color)
				mask = self.miner_icon_mask
			elif entity["type"] == "scout":
				icon = self.colorize(self.scout_icon, color)
				mask = self.scout_icon_mask
			frame[index[0][0]: index[0][1], index[1][0]:index[1][1], :] *= np.abs(mask - 1)
			frame[index[0][0]: index[0][1], index[1][0]:index[1][1], :] += icon / 2 * mask
		return frame

	def render_frames(self, start=0, end=-1):
		frames = []
		arg = (start, end)
		if end == -1:
			arg = (start, len(self.replay["rounds"]))

		for i in tqdm(range(*arg)):
			frames.append(self.make_frame(i))
		self.frames = frames

	def play(self, play_speed=60):
		cv2.imshow('Replay', self.frames[0])
		cv2.waitKey(0)
		for frame in tqdm(self.frames):
			cv2.imshow('Replay', frame)
			cv2.waitKey(play_speed)
		cv2.waitKey(0)
		cv2.destroyAllWindows()

	def save_video(self, out_path, play_speed=1):
		writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), self.default_fps * play_speed, (self.frames[0].shape[0], self.frames[0].shape[1]), True)
		for frame in tqdm(self.frames):
			writer.write(frame)
		writer.release()


if __name__ == "__main__":
	dp = DemoPlayer(15)
	dp.load("./replays/replays-debug.rpl")
	dp.render_frames()
	dp.play(1)
	# dp.save_video("./replays/replays-debug.mp4", 4)

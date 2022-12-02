import json
import random

from core.game import Instance

def main():
	try:
		with open('./config.json', "r", encoding="utf-8") as f:
			config = json.loads(f.read())
			map_file = config['map']
			players = config['players']
			random.shuffle(players)
			rounds = config['rounds']
			game = Instance(players, map_file, rounds)
			game.run()
	except FileNotFoundError:
		print('未找到配置文件。')
		return

if __name__ == '__main__':
	main()

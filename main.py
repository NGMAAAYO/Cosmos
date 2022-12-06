import json
import random

from core.game import Instance


def main():
    try:
        with open('./config.json', "r", encoding="utf-8") as f:
            config = json.loads(f.read())
            map_file = "./maps/{}.json".format(config['map'])
            players = config['players']
            rounds = config['rounds']
            debug = config['debug']

            if debug:
                random.seed(0)
            random.shuffle(players)
            game = Instance(players, map_file, rounds, debug)
            if debug:
                game.replay_path = "./replays/replays-debug.rpl"
            game.run()
    except FileNotFoundError:
        print('未找到配置文件。')
        return


if __name__ == '__main__':
    main()

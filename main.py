import os
import sys
import json
import random

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    # Keep build discovery out of module import: multiprocessing "spawn"
    # imports this file in every child process on Windows and macOS.
    from build_core import ensure_core_built
    ensure_core_built()
    from core.game import Instance

    try:
        with open('./config.json', "r", encoding="utf-8") as f:
            config = json.loads(f.read())
            map_file = "./maps/{}.json".format(config['map'])
            players = config['players']
            rounds = config['rounds']
            debug = config['debug']
            parallel_cores = config.get('parallel_cores', 1)

            if debug:
                random.seed(0)
            random.shuffle(players)
            game = Instance(
                players,
                map_file,
                rounds,
                debug,
                parallel_cores=parallel_cores,
            )
            if debug:
                game.replay_path = "./replays/replays-debug.rpl"
            game.run()
    except FileNotFoundError:
        print('未找到配置文件。')
        return


if __name__ == '__main__':
    main()

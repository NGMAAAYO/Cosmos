import os
import sys
import json
import random

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from build_core import ensure_core_built
ensure_core_built()

from core.game import Instance


def main():
    try:
        with open('./config.json', "r", encoding="utf-8") as f:
            config = json.loads(f.read())
            map_file = "./maps/{}.json".format(config['map'])
            players = config['players']
            rounds = config['rounds']
            debug = config['debug']
            player_runtime = config.get('player_runtime', 'wasm')
            wasm_fuel = int(config.get('wasm_fuel', 100000))
            wasm_host_calls = int(config.get('wasm_host_calls', 10000))
            wasm_max_sensed = int(config.get('wasm_max_sensed', 4096))
            sandbox_seed = int(config.get('sandbox_seed', 0))

            if debug:
                random.seed(0)
            random.shuffle(players)
            game = Instance(
                players, map_file, rounds, debug,
                player_runtime=player_runtime,
                wasm_fuel=wasm_fuel,
                wasm_host_calls=wasm_host_calls,
                wasm_max_sensed=wasm_max_sensed,
                sandbox_seed=sandbox_seed,
            )
            if debug:
                game.replay_path = "./replays/replays-debug.rpl"
            game.run()
    except FileNotFoundError:
        print('未找到配置文件。')
        return


if __name__ == '__main__':
    main()

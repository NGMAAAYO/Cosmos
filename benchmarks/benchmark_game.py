import argparse
import gc
import hashlib
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import EntityType, MapLocation, Team
from core.game import Instance


def make_game(extra_entities, rounds, seed):
	random.seed(seed)
	game = Instance(
		["noact", "noact"],
		"maps/huge_square_x64.json",
		rounds,
		debug=True,
		show_progress=False,
	)
	occupied = {
		(entity.info.location.x, entity.info.location.y)
		for entity in game.entities.values()
	}
	added = 0
	for x in range(game.map.dx, game.map.dx + game.map.width):
		for y in range(game.map.dy, game.map.dy + game.map.height):
			if (x, y) in occupied:
				continue
			game.add_entity(
				EntityType("scout"),
				1,
				MapLocation(x, y),
				Team(str(added % 2)),
			)
			added += 1
			if added == extra_entities:
				return game
	raise ValueError("requested entity count exceeds the available map cells")


def benchmark(extra_entities, rounds, repeats, seed):
	digest = None
	samples = []
	for _ in range(repeats):
		game = make_game(extra_entities, rounds, seed)
		gc.collect()
		started = time.perf_counter()
		for _ in range(rounds):
			game.next_round()
		samples.append(time.perf_counter() - started)
		payload = json.dumps(game.replay, separators=(",", ":"))
		current_digest = hashlib.sha256(payload.encode()).hexdigest()
		if digest is not None and current_digest != digest:
			raise RuntimeError("fixed-seed benchmark produced different replay data")
		digest = current_digest
	return samples, digest


def main():
	parser = argparse.ArgumentParser(description="Benchmark deterministic Cosmos rounds.")
	parser.add_argument("--entities", type=int, default=500, help="extra entities to add")
	parser.add_argument("--rounds", type=int, default=20)
	parser.add_argument("--repeats", type=int, default=3)
	parser.add_argument("--seed", type=int, default=123456)
	args = parser.parse_args()

	samples, digest = benchmark(args.entities, args.rounds, args.repeats, args.seed)
	print(f"entities: {args.entities + 4}")
	print(f"rounds: {args.rounds}")
	print(f"samples_seconds: {samples}")
	print(f"best_seconds: {min(samples):.6f}")
	print(f"replay_sha256: {digest}")


if __name__ == "__main__":
	main()

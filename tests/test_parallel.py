import json
import os
import random
import unittest
from multiprocessing import shared_memory
from unittest import mock

from core import EntityType, MapLocation, Team
from core.game import Instance
from core.parallel import DecisionResult


class ParallelGameTestCase(unittest.TestCase):
	def make_game(self, parallel_cores=2, teams=None):
		random.seed(314159)
		return Instance(
			teams or ["noact", "noact"],
			"maps/maptestsmall.json",
			10,
			debug=True,
			show_progress=False,
			parallel_cores=parallel_cores,
		)

	@staticmethod
	def empty_line(game, length=8):
		occupied = {
			(entity.info.location.x, entity.info.location.y)
			for entity in game.entities.values()
		}
		for x in range(game.map.dx + 1, game.map.dx + game.map.width - length):
			for y in range(game.map.dy + 1, game.map.dy + game.map.height - 1):
				if all((x + offset, y) not in occupied for offset in range(length)):
					return x, y
		raise AssertionError("map does not contain a suitable empty line")

	@staticmethod
	def decision(game, entity_id, action=None, *, location=None, charge_bid=-1):
		entity = game.entities[entity_id]
		info = entity.info
		baseline_location = (info.location.x, info.location.y)
		updated_location = location or baseline_location
		updated_cooldown = entity.cooldown
		if action is not None:
			updated_cooldown += info.type.action_cooldown / game.map.get_aether(*updated_location)
		charge_cost = charge_bid if charge_bid >= 0 else 0
		return DecisionResult(
			round_number=game.round,
			entity_id=entity_id,
			generation=game.entity_generations[entity_id],
			team_code=int(info.team.tag),
			entity_type=info.type.name,
			updated_radio=info.radio,
			cooldown_cost=max(updated_cooldown - entity.cooldown, 0.0),
			primary_action=action,
			charge_bid=charge_bid,
			charge_cost=charge_cost,
		)

	@staticmethod
	def occupied(game):
		return {
			(entity.info.location.x, entity.info.location.y): entity_id
			for entity_id, entity in game.entities.items()
		}

	def test_one_core_preserves_in_process_player_execution(self):
		game = self.make_game(parallel_cores=1)
		self.assertEqual(game.parallel_cores, 1)
		self.assertEqual(len(game.team_instances), 2)
		self.assertIsNone(game._parallel_runtime)
		game.next_round()
		self.assertIsNone(game._parallel_runtime)

	def test_parallel_core_count_is_capped_by_host(self):
		with mock.patch("core.game.os.cpu_count", return_value=2):
			game = self.make_game(parallel_cores=99)
		self.assertEqual(game.parallel_cores, 2)
		self.assertEqual(game.team_instances, [])
		game.close()

	@unittest.skipIf((os.cpu_count() or 1) < 2, "requires at least two CPU cores")
	def test_parallel_snapshot_includes_neutral_map_team(self):
		random.seed(161803)
		game = Instance(
			["noact", "noact", "noact", "noact"],
			"maps/multi_square_x64_4.json",
			1,
			debug=True,
			show_progress=False,
			parallel_cores=2,
		)
		try:
			self.assertIn("Neutral", [team.tag for team in game.all_teams])
			game.next_round()
			self.assertIsNotNone(game._parallel_runtime)
		finally:
			game.close()

	@unittest.skipIf((os.cpu_count() or 1) < 2, "requires at least two CPU cores")
	def test_all_bundled_players_run_in_persistent_workers(self):
		for team_name in ("baseline1", "codex", "example", "misaka17032", "noact", "youmu"):
			with self.subTest(team=team_name):
				random.seed(424242)
				game = Instance(
					[team_name, team_name],
					"maps/maptestsmall.json",
					2,
					debug=True,
					show_progress=False,
					parallel_cores=2,
				)
				try:
					game.next_round()
					game.next_round()
				finally:
					game.close()

	@unittest.skipIf((os.cpu_count() or 1) < 2, "requires at least two CPU cores")
	def test_persistent_workers_execute_a_round_and_release_shared_memory(self):
		game = self.make_game(parallel_cores=2)
		game.next_round()
		runtime = game._parallel_runtime
		self.assertIsNotNone(runtime)
		self.assertEqual(runtime.worker_count, min(2, os.cpu_count() or 1))
		self.assertTrue(all(process.is_alive() for process in runtime._processes))
		shared_name = runtime.snapshot.spec.name
		processes = list(runtime._processes)
		game.close()
		self.assertTrue(all(not process.is_alive() for process in processes))
		with self.assertRaises(FileNotFoundError):
			shared_memory.SharedMemory(name=shared_name)

	@unittest.skipIf((os.cpu_count() or 1) < 2, "requires at least two CPU cores")
	def test_parallel_replay_is_reproducible(self):
		def run_once():
			random.seed(271828)
			game = Instance(
				["example", "example"],
				"maps/maptestsmall.json",
				5,
				debug=True,
				show_progress=False,
				parallel_cores=2,
			)
			try:
				for _ in range(5):
					game.next_round()
				return json.dumps(game.replay, sort_keys=True, separators=(",", ":"))
			finally:
				game.close()

		self.assertEqual(run_once(), run_once())

	def test_destroyed_actor_decision_is_skipped(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		actor_id = game.add_entity(EntityType("miner"), 30, MapLocation(x, y), Team("0"))
		game.entities[actor_id].cooldown = 0
		decision = self.decision(game, actor_id, ("move", 1, 0), location=(x + 1, y))
		game.remove_entity(actor_id)
		game._commit_parallel_decision(decision, self.occupied(game))
		self.assertNotIn(actor_id, game.entities)

	def test_analyze_fails_if_target_moved_out_of_live_range(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		scout_id = game.add_entity(EntityType("scout"), 100, MapLocation(x, y), Team("0"))
		miner_id = game.add_entity(EntityType("miner"), 30, MapLocation(x + 1, y), Team("1"))
		game.entities[scout_id].cooldown = 0
		decision = self.decision(game, scout_id, ("analyze", miner_id))
		original_defence = game.entities[scout_id].info.defence

		game.entities[miner_id].info.location = MapLocation(x + 5, y)
		game.entity_index.sync(miner_id)
		game._commit_parallel_decision(decision, self.occupied(game))

		self.assertIn(miner_id, game.entities)
		self.assertEqual(game.entities[scout_id].info.defence, original_defence)
		self.assertEqual(game.entities[scout_id].cooldown, 0)

	def test_overdrive_still_executes_after_observed_target_moves(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		destroyer_id = game.add_entity(EntityType("destroyer"), 100, MapLocation(x, y), Team("0"))
		target_id = game.add_entity(EntityType("miner"), 30, MapLocation(x + 1, y), Team("1"))
		game.entities[destroyer_id].cooldown = 0
		decision = self.decision(game, destroyer_id, ("overdrive", 1))
		target_defence = game.entities[target_id].info.defence

		game.entities[target_id].info.location = MapLocation(x + 5, y)
		game.entity_index.sync(target_id)
		game._commit_parallel_decision(decision, self.occupied(game))

		self.assertNotIn(destroyer_id, game.entities)
		self.assertIn(target_id, game.entities)
		self.assertEqual(game.entities[target_id].info.defence, target_defence)

	def test_live_occupancy_resolves_conflicting_moves_in_commit_order(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		left_id = game.add_entity(EntityType("miner"), 30, MapLocation(x, y), Team("0"))
		right_id = game.add_entity(EntityType("miner"), 30, MapLocation(x + 2, y), Team("1"))
		game.entities[left_id].cooldown = 0
		game.entities[right_id].cooldown = 0
		left = self.decision(game, left_id, ("move", 1, 0), location=(x + 1, y))
		right = self.decision(game, right_id, ("move", -1, 0), location=(x + 1, y))
		occupied = self.occupied(game)

		game._commit_parallel_decision(left, occupied)
		game._commit_parallel_decision(right, occupied)

		self.assertEqual(game.entities[left_id].info.location, MapLocation(x + 1, y))
		self.assertEqual(game.entities[right_id].info.location, MapLocation(x + 2, y))
		self.assertGreater(game.entities[left_id].cooldown, 0)
		self.assertEqual(game.entities[right_id].cooldown, 0)

	def test_build_conflict_does_not_cancel_independent_charge(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		left_id = game.add_entity(EntityType("planet"), 100, MapLocation(x, y), Team("0"))
		right_id = game.add_entity(EntityType("planet"), 100, MapLocation(x + 2, y), Team("1"))
		left = self.decision(
			game,
			left_id,
			("create", "scout", 1, 0, 10),
			charge_bid=5,
		)
		right = self.decision(
			game,
			right_id,
			("create", "scout", -1, 0, 10),
			charge_bid=5,
		)
		occupied = self.occupied(game)

		game._commit_parallel_decision(left, occupied)
		game._commit_parallel_decision(right, occupied)

		created = [
			entity for entity in game.entities.values()
			if entity.info.location == MapLocation(x + 1, y)
		]
		self.assertEqual(len(created), 1)
		self.assertEqual(game.entities[left_id].info.energy, 85)
		self.assertEqual(game.entities[right_id].info.energy, 95)
		self.assertEqual(game.charge_list[-2:], [(left_id, 5), (right_id, 5)])
		self.assertGreater(game.entities[left_id].cooldown, 0)
		self.assertEqual(game.entities[right_id].cooldown, 0)

	def test_overdrive_conversion_invalidates_stale_target_decision(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		attacker_id = game.add_entity(EntityType("destroyer"), 100, MapLocation(x, y), Team("0"))
		target_id = game.add_entity(EntityType("destroyer"), 20, MapLocation(x + 1, y), Team("1"))
		game.entities[attacker_id].cooldown = 0
		game.entities[target_id].cooldown = 0
		overdrive = self.decision(game, attacker_id, ("overdrive", 1))
		stale_target = self.decision(
			game,
			target_id,
			("move", 1, 0),
			location=(x + 2, y),
		)
		old_generation = game.entity_generations[target_id]
		occupied = self.occupied(game)

		game._commit_parallel_decision(overdrive, occupied)
		game._commit_parallel_decision(stale_target, occupied)

		self.assertEqual(game.entities[target_id].info.team, Team("0"))
		self.assertNotEqual(game.entity_generations[target_id], old_generation)
		self.assertEqual(game.entities[target_id].info.location, MapLocation(x + 1, y))

	def test_radio_commits_without_a_primary_action(self):
		game = self.make_game()
		entity_id = next(
			entity_id for entity_id in game.available_entities_ids
			if game.entities[entity_id].info.team == Team("0")
		)
		decision = self.decision(game, entity_id)
		decision = decision._replace(updated_radio=123456)
		game._commit_parallel_decision(decision, self.occupied(game))
		self.assertEqual(game.entities[entity_id].info.radio, 123456)


if __name__ == "__main__":
	unittest.main()

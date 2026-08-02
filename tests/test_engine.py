import contextlib
import io
import json
import os
import random
import sys
import tempfile
import types
import unittest

from core import Direction, EntityType, MapLocation, Team
from core.cosmos_core import engine_check_round_end, engine_replay_round
from core.game import Instance


class NoActionPlayer:
	@staticmethod
	def run(controller):
		return controller


def install_no_action_module():
	src_package = sys.modules.setdefault("src", types.ModuleType("src"))
	src_package.__path__ = []
	team_package = sys.modules.setdefault("src.noact", types.ModuleType("src.noact"))
	team_package.__path__ = []
	player_module = types.ModuleType("src.noact.main")
	player_module.Player = NoActionPlayer
	sys.modules["src.noact.main"] = player_module


install_no_action_module()


def create_map_file(players=2, size=32, include_neutral=False):
	positions = [(4, 4), (size - 5, size - 5), (4, size - 5), (size - 5, 4)]
	planets = [
		{"x": x, "y": y, "team": str(team), "energy": 150}
		for team, (x, y) in enumerate(positions[:players])
	]
	if include_neutral:
		planets.insert(0, {"x": size // 2, "y": size // 2, "team": "Neutral", "energy": 150})
	payload = {
		"players": players,
		"map_size": [size, size],
		"map": [
			{"x": x, "y": y, "aether": 1.0}
			for x in range(size)
			for y in range(size)
		],
		"planets": planets,
	}
	with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as map_file:
		json.dump(payload, map_file)
		return map_file.name


class EngineTestCase(unittest.TestCase):
	def make_game(self):
		random.seed(24680)
		map_path = create_map_file()
		try:
			return Instance(
				["noact", "noact"],
				map_path,
				10,
				debug=True,
				show_progress=False,
			)
		finally:
			os.unlink(map_path)

	@staticmethod
	def controller_for(game, entity_id):
		return game.entities[entity_id].get_controller(
			game.entity_infos,
			game.all_teams,
			game.charge_result,
			game.map,
			game.round,
			game.overdrive_factor,
		)

	@staticmethod
	def empty_line(game, length=6):
		occupied = {
			(entity.info.location.x, entity.info.location.y)
			for entity in game.entities.values()
		}
		for x in range(game.map.dx + 1, game.map.dx + game.map.width - length):
			for y in range(game.map.dy + 1, game.map.dy + game.map.height - 1):
				if all((x + offset, y) not in occupied for offset in range(length)):
					return x, y
		raise AssertionError("map does not contain a suitable empty line")

	def test_entity_type_attributes_are_read_only(self):
		entity_type = EntityType("scout")
		with self.assertRaises(AttributeError):
			entity_type.name = "destroyer"
		with self.assertRaises(AttributeError):
			entity_type.action_radius = 10_000

	def test_player_must_return_the_provided_controller(self):
		game = self.make_game()
		entity_id = next(rid for rid in game.available_entities_ids if game.entities[rid].info.team == "0")

		class ReplacingPlayer:
			@staticmethod
			def run(controller):
				return object()

		game.entity_instances[entity_id] = ReplacingPlayer()
		with self.assertRaisesRegex(RuntimeError, "Controller"):
			game.run_instance(entity_id)

	def test_non_adjacent_move_and_build_are_rejected(self):
		game = self.make_game()
		planet_id = next(
			rid for rid in game.available_entities_ids
			if game.entities[rid].info.team == "0"
		)
		planet_controller = self.controller_for(game, planet_id)
		invalid_direction = Direction(2, 0)
		self.assertFalse(planet_controller.can_build(EntityType("scout"), invalid_direction, 1))
		with self.assertRaises(RuntimeError):
			planet_controller.build(EntityType("scout"), invalid_direction, 1)

		x, y = self.empty_line(game)
		miner_id = game.add_entity(EntityType("miner"), 10, MapLocation(x, y), Team("0"))
		miner_controller = self.controller_for(game, miner_id)
		self.assertFalse(miner_controller.can_move(invalid_direction))
		with self.assertRaises(RuntimeError):
			miner_controller.move(invalid_direction)

	def test_build_action_snapshot_cannot_be_rewritten(self):
		game = self.make_game()
		planet_id = next(
			rid for rid in game.available_entities_ids
			if game.entities[rid].info.team == "0"
		)
		controller = self.controller_for(game, planet_id)
		direction = next(
			d for d in Direction.all_directions()
			if controller.can_build(EntityType("scout"), d, 1)
		)
		controller.build(EntityType("scout"), direction, 1)

		leaked_create = controller.get_actions()[2][0][1]
		leaked_create[0] = EntityType("destroyer")
		leaked_create[1] = Direction(20, 20)
		leaked_create[2] = 999_999

		fresh_create = controller.get_actions()[2][0][1]
		self.assertEqual(fresh_create[0], "scout")
		self.assertEqual(fresh_create[1], direction)
		self.assertEqual(fresh_create[2], 1)

		previous_ids = set(game.available_entities_ids)
		game.end_instance_check(planet_id, controller)
		created_id = (set(game.available_entities_ids) - previous_ids).pop()
		created = game.entities[created_id].info
		self.assertEqual(created.type, "scout")
		self.assertEqual(created.energy, 1)
		self.assertEqual(created.location, game.entities[planet_id].info.location.add(direction))

	def test_analyze_action_snapshot_and_final_state_are_trusted(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		scout_id = game.add_entity(EntityType("scout"), 100, MapLocation(x, y), Team("0"))
		near_miner_id = game.add_entity(EntityType("miner"), 30, MapLocation(x + 1, y), Team("1"))
		far_miner_id = game.add_entity(EntityType("miner"), 70, MapLocation(x + 5, y), Team("1"))
		game.entities[scout_id].cooldown = 0

		controller = self.controller_for(game, scout_id)
		self.assertTrue(controller.can_analyze(near_miner_id))
		self.assertFalse(controller.can_analyze(far_miner_id))
		controller.analyze(near_miner_id)

		leaked_target = controller.get_actions()[2][0][1]
		leaked_target.ID = far_miner_id
		leaked_target.energy = 999_999
		leaked_target.type = EntityType("planet")

		fresh_target = controller.get_actions()[2][0][1]
		self.assertEqual(fresh_target.ID, near_miner_id)
		self.assertEqual(fresh_target.energy, 30)
		self.assertEqual(fresh_target.type, "miner")

		game.end_instance_check(scout_id, controller)
		self.assertNotIn(near_miner_id, game.entities)
		self.assertIn(far_miner_id, game.entities)
		self.assertEqual(game.overdrive_factor[-1][1], 30)

	def test_neutral_entities_do_not_count_as_surviving_players(self):
		alive, evolutions = engine_check_round_end(
			[1, 2],
			["0", "Neutral"],
			["planet", "planet"],
			[0, 0],
			1,
		)
		self.assertEqual(alive, ["0"])
		self.assertEqual(evolutions, [])

	def test_neutral_planets_do_not_break_final_counting(self):
		random.seed(13579)
		map_path = create_map_file(players=4, size=32, include_neutral=True)
		try:
			game = Instance(
				["noact", "noact", "noact", "noact"],
				map_path,
				1,
				debug=True,
				show_progress=False,
			)
		finally:
			os.unlink(map_path)
		game.save_replay = lambda: None
		with contextlib.redirect_stdout(io.StringIO()):
			winner, reason, _ = game.run()
		self.assertEqual(winner, "None")
		self.assertEqual(reason, "tie")

	def test_replay_frame_matches_per_entity_serialization(self):
		game = self.make_game()
		expected = [info.to_dict() for info in game.entity_infos]
		self.assertEqual(engine_replay_round(game.entity_infos), expected)

	def test_spatial_index_controller_matches_full_scan(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		observer_id = game.add_entity(EntityType("scout"), 50, MapLocation(x, y), Team("0"))
		game.add_entity(EntityType("miner"), 20, MapLocation(x + 1, y), Team("1"))
		game.add_entity(EntityType("destroyer"), 20, MapLocation(x + 5, y), Team("0"))
		game.entity_index.set_order(game.available_entities_ids)
		entity = game.entities[observer_id]
		full_scan = entity.get_controller(
			game.entity_infos, game.all_teams, game.charge_result,
			game.map, game.round, game.overdrive_factor,
		)
		indexed = entity.get_indexed_controller(
			game.entity_index, game.all_teams, game.charge_result,
			game.map, game.round, game.overdrive_factor,
		)
		self.assertEqual(
			[info.to_dict() for info in indexed.sense_nearby_entities()],
			[info.to_dict() for info in full_scan.sense_nearby_entities()],
		)
		self.assertEqual(indexed.detect_nearby_entities(40), full_scan.detect_nearby_entities(40))
		self.assertEqual(indexed.get_entity_count(), full_scan.get_entity_count())


if __name__ == "__main__":
	unittest.main()

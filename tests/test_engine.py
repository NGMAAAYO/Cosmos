import contextlib
import io
import random
import unittest

from core import Direction, EntityType, Map, MapLocation, Team
from core.cosmos_core import (
	engine_check_round_end,
	engine_compute_miner_income,
	engine_get_overdrive_factor,
	engine_process_charge,
	engine_replay_round,
)
from core.game import Instance


class EngineTestCase(unittest.TestCase):
	def make_game(self):
		random.seed(24680)
		return Instance(
			["noact", "noact"],
			"maps/maptestsmall.json",
			10,
			debug=True,
			show_progress=False,
		)

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

	def test_scout_needs_ten_defence_to_analyze_and_can_be_recharged(self):
		game = self.make_game()
		x, y = self.empty_line(game)
		destroyer_id = game.add_entity(EntityType("destroyer"), 100, MapLocation(x, y), Team("0"))
		scout_id = game.add_entity(EntityType("scout"), 100, MapLocation(x + 1, y), Team("0"))
		miner_id = game.add_entity(EntityType("miner"), 30, MapLocation(x + 2, y), Team("1"))
		game.entities[destroyer_id].cooldown = 0
		game.entities[scout_id].cooldown = 0

		game.entities[scout_id].info.defence = 9
		depleted = self.controller_for(game, scout_id)
		self.assertFalse(depleted.can_analyze(miner_id))
		with self.assertRaises(RuntimeError):
			depleted.analyze(miner_id)

		overdrive = self.controller_for(game, destroyer_id)
		overdrive.overdrive(1)
		game.end_instance_check(destroyer_id, overdrive)
		self.assertGreaterEqual(game.entities[scout_id].info.defence, 10)
		self.assertTrue(self.controller_for(game, scout_id).can_analyze(miner_id))

		game.entities[scout_id].info.defence = 10
		recharged = self.controller_for(game, scout_id)
		self.assertTrue(recharged.can_analyze(miner_id))
		recharged.analyze(miner_id)
		self.assertEqual(recharged.get_defence(), 0)

	def test_same_team_planets_tied_for_highest_charge_win_together(self):
		winner, returns = engine_process_charge(
			[(101, 10), (102, 10), (201, 9)],
			["0", "0", "1"],
		)
		self.assertEqual(winner, 0)
		self.assertEqual(returns, [(201, 4)])

		winner, returns = engine_process_charge(
			[(101, 10), (201, 10)],
			["0", "1"],
		)
		self.assertEqual(winner, -1)
		self.assertEqual(returns, [(101, 5), (201, 5)])

	def test_miner_income_is_subcritical_and_paid_by_age(self):
		for energy in (1, 2, 20, 21, 50, 100, 150, 300, 1000, 2000):
			with self.subTest(energy=energy):
				self.assertEqual(engine_compute_miner_income(energy, 49), 0)
				self.assertEqual(engine_compute_miner_income(energy, 301), 0)
				lifetime_income = sum(
					engine_compute_miner_income(energy, age)
					for age in range(50, 301)
				)
				self.assertEqual(lifetime_income, 251 * energy // 300)
				self.assertLess(lifetime_income, energy)

		for energy in range(1, 500):
			current = 251 * energy // 300
			next_value = 251 * (energy + 1) // 300
			self.assertIn(next_value - current, (0, 1))

	def test_scout_boost_uses_one_planet_cycle_and_caps_at_two(self):
		active_until = 100
		self.assertAlmostEqual(
			engine_get_overdrive_factor([("0", 100, active_until)], "0", 1),
			2 ** 0.1,
		)
		self.assertAlmostEqual(
			engine_get_overdrive_factor([("0", 500, active_until)], "0", 1),
			2 ** 0.5,
		)
		self.assertEqual(
			engine_get_overdrive_factor([("0", 1000, active_until)], "0", 1),
			2.0,
		)
		self.assertEqual(
			engine_get_overdrive_factor([("0", 5000, active_until)], "0", 1),
			2.0,
		)
		self.assertEqual(
			engine_get_overdrive_factor([("0", 1000, 1)], "0", 1),
			1.0,
		)

		game = self.make_game()
		game.round = 1
		game.overdrive_factor = [("0", 1000, active_until)]
		team_zero_planet = next(
			entity_id for entity_id in game.available_entities_ids
			if game.entities[entity_id].info.team == Team("0")
		)
		controller = self.controller_for(game, team_zero_planet)
		self.assertEqual(controller.get_overdrive_factor(Team("0")), 2.0)

	def test_map_aether_density_is_clamped_to_minimum(self):
		game_map = Map(
			[
				{"x": 0, "y": 0, "aether": 0.0},
				{"x": 1, "y": 0, "aether": -1.0},
				{"x": 0, "y": 1, "aether": 0.5},
			],
			(2, 2),
		)
		self.assertEqual(game_map.get_aether(0, 0), 0.0001)
		self.assertEqual(game_map.get_aether(1, 0), 0.0001)
		self.assertEqual(game_map.get_aether(1, 1), 0.0001)
		self.assertEqual(game_map.get_aether(0, 1), 0.5)

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
		game = Instance(
			["noact", "noact", "noact", "noact"],
			"maps/multi_square_x64_4.json",
			1,
			debug=True,
			show_progress=False,
		)
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

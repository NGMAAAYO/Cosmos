import importlib.util
import json
import random
import tempfile
import unittest
from pathlib import Path

from core.game import Instance
from core.wasm_sandbox import (
	SandboxCompileError,
	SandboxLimits,
	SandboxTurnAborted,
	WasmRuntime,
	compile_restricted_python,
)


WASMTIME_AVAILABLE = importlib.util.find_spec("wasmtime") is not None


class FakeController:
	def __init__(self):
		self.radio = 0

	def sense_nearby_entities(self):
		return []

	def set_radio(self, value):
		self.radio = value

	def get_energy(self):
		return 100


@unittest.skipUnless(WASMTIME_AVAILABLE, "wasmtime is not installed")
class WasmSandboxTestCase(unittest.TestCase):
	@staticmethod
	def write_players(root, sources):
		for team, source in sources.items():
			team_dir = Path(root, team)
			team_dir.mkdir()
			team_dir.joinpath("main.py").write_text(source, encoding="utf-8")

	@staticmethod
	def write_map(root, size=16):
		payload = {
			"players": 2,
			"map_size": [size, size],
			"map": [
				{"x": x, "y": y, "aether": 1.0}
				for x in range(size)
				for y in range(size)
			],
			"planets": [
				{"x": 2, "y": 2, "team": "0", "energy": 150},
				{"x": size - 3, "y": size - 3, "team": "1", "energy": 150},
			],
		}
		map_path = Path(root, "map.json")
		map_path.write_text(json.dumps(payload), encoding="utf-8")
		return str(map_path)

	def test_forbidden_python_features_are_rejected(self):
		invalid_sources = (
			"import os\nclass Player:\n pass\n",
			"shared = 1\nclass Player:\n pass\n",
			"class Player:\n shared = 1\n",
			"class Player:\n def run(self, controller):\n  open('/tmp/x')\n",
			"class Player:\n def run(self, controller):\n  return getattr(controller, 'get_energy')\n",
			"class Player:\n def helper(self, value):\n  return value\n def run(self, controller):\n  self.helper()\n",
			"class Player:\n def helper(self):\n  self.helper()\n def run(self, controller):\n  self.helper()\n",
			"class Player:\n def run_planet(self, unexpected):\n  pass\n",
		)
		for source in invalid_sources:
			with self.subTest(source=source), self.assertRaises(SandboxCompileError):
				compile_restricted_python(source)

	def test_generated_module_has_only_explicit_cosmos_imports_and_no_memory(self):
		import wasmtime

		source = """
class Player:
    def run(self, controller):
        if controller.can_set_radio(7):
            controller.set_radio(7)
"""
		wat = compile_restricted_python(source)
		module = wasmtime.Module(wasmtime.Engine(), wat)
		self.assertTrue(module.imports)
		self.assertTrue(all(item.module == "cosmos" for item in module.imports))
		self.assertEqual([item.name for item in module.imports], ["can_set_radio", "set_radio"])
		self.assertNotIn("memory", {item.name for item in module.exports})

	def test_host_calls_have_a_separate_budget(self):
		source = """
class Player:
    def run(self, controller):
        for _ in range(100):
            controller.get_energy()
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source})
			limits = SandboxLimits(fuel_per_turn=100_000, max_host_calls_per_turn=3)
			player = WasmRuntime(limits).compile_team("alpha", root).create_player(1, "0")
			with self.assertRaises(SandboxTurnAborted) as trapped:
				player.run(FakeController())
			self.assertFalse(trapped.exception.out_of_fuel)

	def test_source_size_and_team_path_are_bounded_before_compilation(self):
		with tempfile.TemporaryDirectory() as root:
			team_dir = Path(root, "alpha")
			team_dir.mkdir()
			team_dir.joinpath("main.py").write_text("#" * 128, encoding="utf-8")
			runtime = WasmRuntime(SandboxLimits(max_source_bytes=64))
			with self.assertRaisesRegex(ValueError, "source exceeds"):
				runtime.compile_team("alpha", root)
			with self.assertRaisesRegex(ValueError, "invalid team name"):
				runtime.compile_team("../alpha", root)

	def test_each_entity_has_isolated_persistent_globals(self):
		source = """
class Player:
    def __init__(self):
        self.counter = 0

    def run(self, controller):
        self.counter += 1
        controller.set_radio(self.counter)
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source})
			team = WasmRuntime(seed=123).compile_team("alpha", root)
			first = team.create_player(10001, "0")
			second = team.create_player(10002, "0")
			first_controller = FakeController()
			second_controller = FakeController()
			first.run(first_controller)
			second.run(second_controller)
			self.assertEqual((first_controller.radio, second_controller.radio), (1, 1))
			first.run(first_controller)
			self.assertEqual(first_controller.radio, 2)
			self.assertEqual(second_controller.radio, 1)

	def test_none_sentinel_does_not_alias_a_valid_direction(self):
		source = """
from core.api import *

class Player:
    def __init__(self):
        self.direction = None

    def run(self, controller):
        if self.direction is None:
            self.direction = Direction.south_west()
            controller.set_radio(1)
        else:
            controller.set_radio(2)
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source})
			player = WasmRuntime().compile_team("alpha", root).create_player(1, "0")
			controller = FakeController()
			player.run(controller)
			self.assertEqual(controller.radio, 1)
			player.run(controller)
			self.assertEqual(controller.radio, 2)

	def test_cpython_integer_bit_helpers_are_lowered_for_micropython(self):
		source = """
class Player:
    def run(self, controller):
        positive = (1 << 63) | (1 << 2)
        negative = -positive
        controller.set_radio(positive.bit_length() + negative.bit_count())
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source})
			player = WasmRuntime().compile_team("alpha", root).create_player(1, "0")
			controller = FakeController()
			player.run(controller)
			self.assertEqual(controller.radio, 66)

	def test_fuel_exhaustion_discards_partial_action_and_rolls_back_state(self):
		looping = """
class Player:
    def __init__(self):
        self.turns = 0

    def run(self, controller):
        self.turns += 1
        if self.turns == 1:
            controller.set_radio(999)
            while True:
                pass
        controller.set_radio(5)
"""
		healthy = """
class Player:
    def run(self, controller):
        controller.set_radio(7)
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"looping": looping, "healthy": healthy})
			map_path = self.write_map(root)
			random.seed(2468)
			game = Instance(
				["looping", "healthy"], map_path, 2,
				debug=True, show_progress=False,
				player_runtime="wasm", wasm_fuel=1_000,
				sandbox_seed=99, player_root=root,
			)
			looping_id, healthy_id = game.planet_list
			game.run_instance(looping_id)
			game.run_instance(healthy_id)
			self.assertEqual(game.entities[looping_id].info.radio, 0)
			self.assertEqual(game.entities[healthy_id].info.radio, 7)
			self.assertEqual(game.sandbox_aborts[looping_id], 1)
			game.run_instance(looping_id)
			self.assertEqual(game.entities[looping_id].info.radio, 0)
			self.assertEqual(game.sandbox_aborts[looping_id], 2)

	def test_instance_defaults_to_the_wasm_runtime(self):
		source = "class Player:\n    def run(self, controller):\n        controller.set_radio(11)\n"
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source, "beta": source})
			map_path = self.write_map(root)
			random.seed(97531)
			game = Instance(
				["alpha", "beta"], map_path, 1,
				debug=True, show_progress=False, player_root=root,
			)
			entity_id = game.planet_list[0]
			game.run_instance(entity_id)
			self.assertEqual(game.player_runtime, "wasm")
			self.assertEqual(game.entities[entity_id].info.radio, 11)

	def test_template_style_type_dispatch_is_compiled_without_importing_template(self):
		source = """
from src import template
from core.api import *

class Player(template.Player):
    def __init__(self):
        super().__init__()
        self.turns = 0

    def run_planet(self):
        self.turns += 1
        self.controller.set_radio(self.turns)
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source, "beta": source})
			map_path = self.write_map(root)
			random.seed(8642)
			game = Instance(
				["alpha", "beta"], map_path, 1,
				debug=True, show_progress=False, player_root=root,
			)
			entity_id = game.planet_list[0]
			game.run_instance(entity_id)
			self.assertEqual(game.entities[entity_id].info.radio, 1)

	def test_sensed_entities_are_read_through_bounded_handles(self):
		source = """
from core.api import *

class Player:
    def run(self, controller):
        for entity in controller.sense_nearby_entities(teams=controller.get_opponent()):
            controller.set_radio(entity.ID)
            return
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source, "beta": source})
			map_path = self.write_map(root, size=8)
			random.seed(1357)
			game = Instance(
				["alpha", "beta"], map_path, 1,
				debug=True, show_progress=False,
				player_runtime="wasm", wasm_fuel=10_000,
				player_root=root,
			)
			first_id, second_id = game.planet_list
			game.run_instance(first_id)
			self.assertEqual(game.entities[first_id].info.radio, second_id)

	def test_deterministic_per_entity_random_does_not_use_python_random(self):
		source = """
class Player:
    def run(self, controller):
        controller.set_radio(controller.random_int(1000000))
"""
		with tempfile.TemporaryDirectory() as root:
			self.write_players(root, {"alpha": source})
			team = WasmRuntime(SandboxLimits(fuel_per_turn=10_000), seed=456).compile_team("alpha", root)
			one = team.create_player(12345, "0")
			two = team.create_player(12345, "0")
			first_controller = FakeController()
			second_controller = FakeController()
			random.seed(1)
			one.run(first_controller)
			random.seed(999999)
			two.run(second_controller)
			self.assertEqual(first_controller.radio, second_controller.radio)


if __name__ == "__main__":
	unittest.main()

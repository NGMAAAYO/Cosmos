import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from core.wasm_sandbox import SandboxLimits, SandboxTurnAborted
from core.wasm_sandbox.py2wasm import Py2WasmCompileError, Py2WasmCompiler, Py2WasmRuntime
from core.wasm_sandbox.py2wasm.policy import PlayerPolicyError, validate_team_sources


WASMTIME_AVAILABLE = importlib.util.find_spec("wasmtime") is not None


class FakeController:
	def __init__(self):
		self.radio = 0

	def sense_nearby_entities(self):
		return []

	def set_radio(self, value):
		self.radio = value


class Py2WasmPolicyTestCase(unittest.TestCase):
	@staticmethod
	def write_team(root, source, extra=None):
		team = Path(root, "alpha")
		team.mkdir()
		team.joinpath("main.py").write_text(source, encoding="utf-8")
		for name, content in (extra or {}).items():
			team.joinpath(name).write_text(content, encoding="utf-8")

	def test_checked_in_strategies_pass_the_source_policy(self):
		for team in ("baseline1", "codex", "example", "misaka17032", "noact", "youmu"):
			with self.subTest(team=team):
				files = validate_team_sources(team)
				self.assertIn(f"{team}/main.py", files)

	def test_local_modules_and_approved_standard_library_are_allowed(self):
		with tempfile.TemporaryDirectory() as root:
			self.write_team(
				root,
				"from src.alpha.helper import choose\nimport math\nimport random\nclass Player:\n    pass\n",
				{"helper.py": "def choose(): return 1\n"},
			)
			files = validate_team_sources("alpha", root)
			self.assertEqual(set(files), {"alpha/main.py", "alpha/helper.py"})

	def test_capability_and_reflection_escape_paths_are_rejected(self):
		invalid = (
			"import os\nclass Player: pass\n",
			"class Player:\n def run(self, c): return __builtins__['open']('/tmp/x')\n",
			"from core.api import _raw_call\nclass Player: pass\n",
			"import core.api\nclass Player:\n def run(self, c): return core.api._raw_call(1)\n",
			"import math\nclass Player:\n def run(self, c): return math.__loader__\n",
			"class Player:\n def run(self, c): return open('/tmp/x')\n",
			"class Player:\n def run(self, c): return c.__class__.__mro__\n",
			"class Player:\n def run(self, c): return getattr(c, 'get_energy')\n",
		)
		for source in invalid:
			with self.subTest(source=source), tempfile.TemporaryDirectory() as root:
				self.write_team(root, source)
				with self.assertRaises(PlayerPolicyError):
					validate_team_sources("alpha", root)

	def test_symlinked_player_source_is_rejected(self):
		with tempfile.TemporaryDirectory() as root:
			team = Path(root, "alpha")
			team.mkdir()
			outside = Path(root, "outside.py")
			outside.write_text("class Player: pass\n", encoding="utf-8")
			try:
				os.symlink(outside, team.joinpath("main.py"))
			except OSError:
				self.skipTest("symlinks are unavailable")
			with self.assertRaises(PlayerPolicyError):
				validate_team_sources("alpha", root)


@unittest.skipUnless(WASMTIME_AVAILABLE, "wasmtime is not installed")
class Py2WasmRuntimeTestCase(unittest.TestCase):
	@staticmethod
	def runtime_for(wat, fuel=100_000):
		import wasmtime

		artifact = Py2WasmCompiler.inspect(wasmtime.wat2wasm(wat))

		class Compiler:
			def compile_team(self, *args):
				return artifact

		limits = SandboxLimits(
			fuel_per_turn=fuel,
			max_guest_memory=4 * 1024 * 1024,
			max_wasm_stack=512 * 1024,
		)
		return Py2WasmRuntime(limits, compiler=Compiler())

	def test_each_entity_has_an_isolated_persistent_instance(self):
		wat = """
(module
  (import "cosmos" "call" (func $call (param i32 i64 i64 i64) (result i64)))
  (import "cosmos" "call_float" (func (param i32 i64 i64 i64) (result f64)))
  (memory (export "memory") 1)
  (func (export "_start"))
  (func (export "cosmos_turn") (result i32)
    i32.const 0
    i32.const 0
    i64.load
    i64.const 1
    i64.add
    i64.store
    i32.const 40
    i32.const 0
    i64.load
    i64.const 0
    i64.const 0
    call $call
    drop
    i32.const 0))
"""
		team = self.runtime_for(wat).compile_team("alpha")
		first = team.create_player(1, "0")
		second = team.create_player(2, "0")
		first_controller = FakeController()
		second_controller = FakeController()
		first.run(first_controller)
		second.run(second_controller)
		self.assertEqual((first_controller.radio, second_controller.radio), (1, 1))
		first.run(first_controller)
		self.assertEqual(first_controller.radio, 2)

	def test_fuel_timeout_resets_linear_memory(self):
		wat = """
(module
  (import "cosmos" "call" (func $call (param i32 i64 i64 i64) (result i64)))
  (import "cosmos" "call_float" (func (param i32 i64 i64 i64) (result f64)))
  (memory (export "memory") 1)
  (func (export "_start"))
  (func (export "cosmos_turn") (result i32)
    i32.const 0
    i32.const 0
    i64.load
    i64.const 1
    i64.add
    i64.store
    i32.const 40
    i32.const 0
    i64.load
    i64.const 0
    i64.const 0
    call $call
    drop
    (loop $forever br $forever)
    i32.const 0))
"""
		player = self.runtime_for(wat, fuel=1_000).compile_team("alpha").create_player(1, "0")
		controller = FakeController()
		for _ in range(2):
			with self.assertRaises(SandboxTurnAborted) as trapped:
				player.run(controller)
			self.assertTrue(trapped.exception.out_of_fuel)
			self.assertEqual(controller.radio, 1)

	def test_artifact_rejects_exports_outside_the_runtime_abi(self):
		import wasmtime

		wat = """
(module
  (import "cosmos" "call" (func (param i32 i64 i64 i64) (result i64)))
  (import "cosmos" "call_float" (func (param i32 i64 i64 i64) (result f64)))
  (memory (export "memory") 1)
  (func (export "_start"))
  (func (export "cosmos_turn") (result i32) i32.const 0)
  (func (export "unexpected")))
"""
		with self.assertRaises(Py2WasmCompileError):
			Py2WasmCompiler.inspect(wasmtime.wat2wasm(wat))


if __name__ == "__main__":
	unittest.main()

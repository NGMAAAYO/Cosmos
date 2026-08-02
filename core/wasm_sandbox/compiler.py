"""Compile a deliberately small Python strategy language to WebAssembly text.

The source is parsed as Python for familiarity, but it is never imported or
executed by CPython.  Only the syntax implemented below is accepted.  The
generated module has no memory, table, WASI imports, or indirect calls.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ENTITY_TYPES = {
	"planet": 0,
	"destroyer": 1,
	"miner": 2,
	"scout": 3,
}

NONE_SENTINEL = -(1 << 63)
MAX_METHODS = 256
MAX_METHOD_PARAMETERS = 16
MAX_STATE_FIELDS = 256
MAX_LOCALS_PER_METHOD = 512

DIRECTIONS = {
	"center": 4,
	"north": 5,
	"north_east": 8,
	"east": 7,
	"south_east": 6,
	"south": 3,
	"south_west": 0,
	"west": 1,
	"north_west": 2,
}


@dataclass(frozen=True)
class HostImport:
	name: str
	params: int


# Every host function returns one i64.  Keeping a single scalar ABI makes the
# generated modules easy to validate and avoids guest-controlled memory.
HOST_IMPORTS: Tuple[HostImport, ...] = tuple(
	HostImport(name, params)
	for name, params in (
		("get_round_num", 0),
		("get_cooldown_turns", 0),
		("get_energy", 0),
		("get_defence", 0),
		("get_id", 0),
		("get_location", 0),
		("get_team", 0),
		("get_type", 0),
		("get_radio", 0),
		("get_charge_point", 0),
		("get_entity_count", 0),
		("is_ready", 0),
		("is_opponent", 1),
		("is_blocked", 1),
		("is_location_occupied", 1),
		("on_the_map", 1),
		("can_detect_location", 1),
		("can_detect_radius", 1),
		("can_sense_location", 1),
		("can_sense_radius", 1),
		("can_charge", 1),
		("can_build", 3),
		("can_overdrive", 1),
		("can_analyze_id", 1),
		("can_analyze_location", 1),
		("can_move", 1),
		("can_set_radio", 1),
		("charge", 1),
		("build", 3),
		("overdrive", 1),
		("analyze_id", 1),
		("analyze_location", 1),
		("move", 1),
		("set_radio", 1),
		("sense_count", 0),
		("sense_id", 1),
		("sense_energy", 1),
		("sense_defence", 1),
		("sense_location", 1),
		("sense_team", 1),
		("sense_type", 1),
		("sense_radio", 1),
		("location_make", 2),
		("location_x", 1),
		("location_y", 1),
		("location_add", 2),
		("location_subtract", 2),
		("location_translate", 3),
		("location_direction_to", 2),
		("location_distance_to", 2),
		("location_is_adjacent_to", 2),
		("direction_make", 2),
		("direction_dx", 1),
		("direction_dy", 1),
		("direction_opposite", 1),
		("direction_rotate_left", 1),
		("direction_rotate_right", 1),
		("direction_all_at", 1),
		("direction_cardinal_at", 1),
		("type_action_radius", 1),
		("type_detection_radius", 1),
		("type_initial_cooldown", 1),
		("type_sensor_radius", 1),
		("random_int", 1),
	)
)


CONTROLLER_METHODS = {
	"get_round_num": ("get_round_num", "int"),
	"get_cooldown_turns": ("get_cooldown_turns", "int"),
	"get_energy": ("get_energy", "int"),
	"get_defence": ("get_defence", "int"),
	"get_id": ("get_id", "int"),
	"get_location": ("get_location", "location"),
	"get_team": ("get_team", "team"),
	"get_type": ("get_type", "entity_type"),
	"get_radio": ("get_radio", "int"),
	"get_charge_point": ("get_charge_point", "int"),
	"get_entity_count": ("get_entity_count", "int"),
	"is_ready": ("is_ready", "bool"),
	"is_opponent": ("is_opponent", "bool"),
	"is_blocked": ("is_blocked", "bool"),
	"is_location_occupied": ("is_location_occupied", "bool"),
	"on_the_map": ("on_the_map", "bool"),
	"can_detect_location": ("can_detect_location", "bool"),
	"can_detect_radius": ("can_detect_radius", "bool"),
	"can_sense_location": ("can_sense_location", "bool"),
	"can_sense_radius": ("can_sense_radius", "bool"),
	"can_charge": ("can_charge", "bool"),
	"can_build": ("can_build", "bool"),
	"can_overdrive": ("can_overdrive", "bool"),
	"can_move": ("can_move", "bool"),
	"can_set_radio": ("can_set_radio", "bool"),
	"charge": ("charge", "int"),
	"build": ("build", "int"),
	"overdrive": ("overdrive", "int"),
	"move": ("move", "int"),
	"set_radio": ("set_radio", "int"),
	"random_int": ("random_int", "int"),
}


class SandboxCompileError(ValueError):
	"""Raised when player source uses syntax outside the sandbox language."""


def _wat_name(name: str) -> str:
	if not name.isidentifier() or name.startswith("__"):
		raise SandboxCompileError(f"invalid identifier: {name!r}")
	return name


class RestrictedPythonCompiler:
	def __init__(
		self,
		source: str,
		filename: str = "<player>",
		*,
		max_source_bytes: int = 128 * 1024,
		max_ast_nodes: int = 20_000,
		max_ast_depth: int = 80,
	):
		self.source = source
		self.filename = filename
		if len(source.encode("utf-8")) > max_source_bytes:
			raise SandboxCompileError(f"{filename}: source exceeds {max_source_bytes} bytes")
		try:
			self.tree = ast.parse(source, filename=filename)
		except SyntaxError as exc:
			raise SandboxCompileError(str(exc)) from exc
		nodes = list(ast.walk(self.tree))
		if len(nodes) > max_ast_nodes:
			raise SandboxCompileError(f"{filename}: AST exceeds {max_ast_nodes} nodes")
		if self._depth(self.tree) > max_ast_depth:
			raise SandboxCompileError(f"{filename}: AST nesting exceeds {max_ast_depth}")
		self.player_class: Optional[ast.ClassDef] = None
		self.methods: Dict[str, ast.FunctionDef] = {}
		self.state_values: Dict[str, int] = {}
		self.state_types: Dict[str, str] = {}
		self._parse_module()

	@staticmethod
	def _depth(node: ast.AST) -> int:
		children = list(ast.iter_child_nodes(node))
		return 1 if not children else 1 + max(RestrictedPythonCompiler._depth(child) for child in children)

	def error(self, node: ast.AST, message: str):
		line = getattr(node, "lineno", "?")
		column = getattr(node, "col_offset", "?")
		raise SandboxCompileError(f"{self.filename}:{line}:{column}: {message}")

	def _parse_module(self):
		for statement in self.tree.body:
			if isinstance(statement, ast.ImportFrom):
				if statement.module == "core.api" and all(alias.name == "*" for alias in statement.names):
					continue
				if statement.module == "src" and [alias.name for alias in statement.names] == ["template"]:
					continue
				self.error(statement, "imports are disabled; only the declarative core.api/template imports are accepted")
			if isinstance(statement, ast.ClassDef) and statement.name == "Player":
				if self.player_class is not None:
					self.error(statement, "exactly one Player class is allowed")
				self.player_class = statement
				continue
			if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
				continue
			self.error(statement, "module globals and executable module statements are forbidden")
		if self.player_class is None:
			raise SandboxCompileError(f"{self.filename}: missing Player class")
		self._parse_player_class(self.player_class)

	def _parse_player_class(self, player: ast.ClassDef):
		if player.decorator_list or player.keywords:
			self.error(player, "decorators and class keywords are forbidden")
		for base in player.bases:
			valid = (
				isinstance(base, ast.Name) and base.id == "object"
			) or (
				isinstance(base, ast.Attribute)
				and isinstance(base.value, ast.Name)
				and base.value.id == "template"
				and base.attr == "Player"
			)
			if not valid:
				self.error(base, "Player may only inherit from template.Player")
		for statement in player.body:
			if isinstance(statement, ast.FunctionDef):
				if len(self.methods) >= MAX_METHODS:
					self.error(statement, f"Player exceeds {MAX_METHODS} methods")
				if statement.name in self.methods:
					self.error(statement, f"duplicate method {statement.name}")
				self._validate_method_signature(statement)
				self.methods[statement.name] = statement
			elif isinstance(statement, ast.Pass):
				continue
			elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
				continue
			else:
				self.error(statement, "class variables and dynamic class statements are forbidden")
		initializer = self.methods.pop("__init__", None)
		if initializer is not None:
			self._parse_initializer(initializer)
		self._validate_method_calls()

	def _method_arity(self, name: str) -> int:
		method = self.methods[name]
		parameters = [argument.arg for argument in method.args.args[1:]]
		if name == "run" and parameters and parameters[0] in {"controller", "api"}:
			parameters.pop(0)
		return len(parameters)

	def _validate_method_calls(self):
		for entrypoint in ("run_planet", "run_destroyer", "run_miner", "run_scout"):
			if entrypoint in self.methods and self._method_arity(entrypoint) != 0:
				self.error(self.methods[entrypoint], f"{entrypoint} may only accept self")
		if "run" in self.methods and self._method_arity("run") != 0:
			self.error(self.methods["run"], "run may only accept self and an optional controller/api parameter")

		call_graph = {name: set() for name in self.methods}
		for owner, method in self.methods.items():
			for node in ast.walk(method):
				if not (
					isinstance(node, ast.Call)
					and isinstance(node.func, ast.Attribute)
					and isinstance(node.func.value, ast.Name)
					and node.func.value.id == "self"
				):
					continue
				target = node.func.attr
				if target == "controller":
					continue
				if target not in self.methods:
					self.error(node, f"unknown helper method {target!r}")
				if node.keywords or len(node.args) != self._method_arity(target):
					self.error(node, f"{target} requires {self._method_arity(target)} positional arguments")
				call_graph[owner].add(target)

		visiting = set()
		visited = set()

		def visit(name: str):
			if name in visiting:
				self.error(self.methods[name], "recursive helper calls are forbidden")
			if name in visited:
				return
			visiting.add(name)
			for target in call_graph[name]:
				visit(target)
			visiting.remove(name)
			visited.add(name)

		for method_name in self.methods:
			visit(method_name)

	def _validate_method_signature(self, method: ast.FunctionDef):
		if method.name != "__init__":
			_wat_name(method.name)
		args = method.args
		if method.decorator_list or args.posonlyargs or args.vararg or args.kwarg or args.kwonlyargs or args.defaults:
			self.error(method, "only plain positional method parameters are supported")
		if not args.args or args.args[0].arg != "self":
			self.error(method, "the first method parameter must be self")
		if len(args.args) - 1 > MAX_METHOD_PARAMETERS:
			self.error(method, f"methods may have at most {MAX_METHOD_PARAMETERS} parameters after self")
		for argument in args.args:
			_wat_name(argument.arg)

	def _parse_initializer(self, initializer: ast.FunctionDef):
		if len(initializer.args.args) != 1:
			self.error(initializer, "__init__ only accepts self")
		for statement in initializer.body:
			if isinstance(statement, ast.Pass):
				continue
			if isinstance(statement, ast.Expr) and self._is_super_init(statement.value):
				continue
			if isinstance(statement, (ast.Assign, ast.AnnAssign)):
				target = statement.targets[0] if isinstance(statement, ast.Assign) and len(statement.targets) == 1 else getattr(statement, "target", None)
				value = statement.value
				if self._is_self_attribute(target):
					name = target.attr
					if name == "controller":
						continue
					_wat_name(name)
					if name in self.state_values:
						self.error(target, f"duplicate state field {name}")
					if len(self.state_values) >= MAX_STATE_FIELDS:
						self.error(target, f"Player exceeds {MAX_STATE_FIELDS} persistent fields")
					constant, value_type = self._constant_value(value)
					self.state_values[name] = constant
					self.state_types[name] = value_type
					continue
			self.error(statement, "__init__ may only initialize scalar self fields with constants")

	@staticmethod
	def _is_super_init(node: ast.AST) -> bool:
		return (
			isinstance(node, ast.Call)
			and isinstance(node.func, ast.Attribute)
			and node.func.attr == "__init__"
			and isinstance(node.func.value, ast.Call)
			and isinstance(node.func.value.func, ast.Name)
			and node.func.value.func.id == "super"
		)

	@staticmethod
	def _is_self_attribute(node: Optional[ast.AST]) -> bool:
		return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self"

	def _constant_value(self, node: ast.AST) -> Tuple[int, str]:
		if isinstance(node, ast.Constant):
			if node.value is None:
				return NONE_SENTINEL, "unknown"
			if isinstance(node.value, bool):
				return int(node.value), "bool"
			if isinstance(node.value, int):
				return self._check_i64(node.value, node), "int"
		if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int):
			return self._check_i64(-node.operand.value, node), "int"
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
			if node.func.id == "EntityType" and len(node.args) == 1 and isinstance(node.args[0], ast.Constant):
				name = node.args[0].value
				if name in ENTITY_TYPES:
					return ENTITY_TYPES[name], "entity_type"
			if node.func.id == "Direction" and len(node.args) == 2:
				dx, _ = self._constant_value(node.args[0])
				dy, _ = self._constant_value(node.args[1])
				if -1 <= dx <= 1 and -1 <= dy <= 1:
					return (dx + 1) * 3 + (dy + 1), "direction"
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
			if node.func.value.id == "Direction" and node.func.attr in DIRECTIONS and not node.args and not node.keywords:
				return DIRECTIONS[node.func.attr], "direction"
		self.error(node, "state initializers must be scalar constants")

	@staticmethod
	def _check_i64(value: int, node: ast.AST) -> int:
		if value < -(1 << 63) or value >= (1 << 63):
			raise SandboxCompileError(f"line {getattr(node, 'lineno', '?')}: integer is outside signed i64")
		return value

	def compile(self) -> str:
		globals_wat = [
			f'  (global $state_{name} (export "__state_{name}") (mut i64) (i64.const {value}))'
			for name, value in sorted(self.state_values.items())
		]
		functions = []
		for name, method in self.methods.items():
			functions.append(FunctionCompiler(self, name, method).compile())
		functions.append(self._compile_dispatch())
		function_text = "\n".join(functions)
		used_imports = {
			line.split("$api_", 1)[1].split()[0]
			for line in function_text.splitlines()
			if "$api_" in line
		}
		imports = []
		for spec in HOST_IMPORTS:
			if spec.name not in used_imports:
				continue
			params = "".join(" (param i64)" for _ in range(spec.params))
			imports.append(f'  (import "cosmos" "{spec.name}" (func $api_{spec.name}{params} (result i64)))')
		return "\n".join(["(module", *imports, *globals_wat, *functions, ")", ""])

	def _compile_dispatch(self) -> str:
		if "run" in self.methods:
			return "\n".join((
				'  (func (export "run")',
				"    call $fn_run",
				"    drop",
				"  )",
			))
		lines = ['  (func (export "run")']
		for method_name, type_name in (
			("run_planet", "planet"),
			("run_destroyer", "destroyer"),
			("run_miner", "miner"),
			("run_scout", "scout"),
		):
			if method_name not in self.methods:
				continue
			lines.extend((
				"    call $api_get_type",
				f"    i64.const {ENTITY_TYPES[type_name]}",
				"    i64.eq",
				"    if",
				f"      call $fn_{method_name}",
				"      drop",
				"    end",
			))
		lines.append("  )")
		return "\n".join(lines)


class FunctionCompiler:
	def __init__(self, compiler: RestrictedPythonCompiler, name: str, method: ast.FunctionDef):
		self.compiler = compiler
		self.name = name
		self.method = method
		self.params: List[str] = []
		self.local_types: Dict[str, str] = {}
		self.temp_counter = 0
		self.label_counter = 0
		self.break_labels: List[str] = []
		self.continue_labels: List[str] = []
		args = [argument.arg for argument in method.args.args[1:]]
		if name == "run" and args and args[0] in {"controller", "api"}:
			self.local_types[args.pop(0)] = "controller"
		self.params = args
		for parameter in args:
			self.local_types[parameter] = "int"
		for node in ast.walk(method):
			if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id not in self.params:
				_wat_name(node.id)
				self.local_types.setdefault(node.id, "int")

	def compile(self) -> str:
		body: List[str] = []
		for statement in self.method.body:
			body.extend(self.emit_statement(statement))
		body.append("i64.const 0")
		if len(self.local_types) > MAX_LOCALS_PER_METHOD:
			self.error(self.method, f"method exceeds {MAX_LOCALS_PER_METHOD} locals and compiler temporaries")
		params = "".join(f" (param ${name} i64)" for name in self.params)
		implicit = {argument.arg for argument in self.method.args.args[1:]} - set(self.params)
		locals_wat = "".join(
			f" (local ${name} i64)"
			for name in self.local_types
			if name not in self.params and name not in implicit
		)
		lines = [f"  (func $fn_{self.name}{params} (result i64){locals_wat}"]
		lines.extend(f"    {line}" for line in body)
		lines.append("  )")
		return "\n".join(lines)

	def error(self, node: ast.AST, message: str):
		self.compiler.error(node, message)

	def new_temp(self, value_type: str = "int") -> str:
		name = f"__sandbox_tmp_{self.temp_counter}"
		self.temp_counter += 1
		self.local_types[name] = value_type
		return name

	def new_label(self, prefix: str) -> str:
		name = f"{prefix}_{self.label_counter}"
		self.label_counter += 1
		return name

	@staticmethod
	def truthy(lines: List[str]) -> List[str]:
		return [*lines, "i64.const 0", "i64.ne"]

	@staticmethod
	def i32_to_i64(lines: List[str]) -> List[str]:
		return [*lines, "i64.extend_i32_u"]

	def emit_statement(self, node: ast.stmt) -> List[str]:
		if isinstance(node, ast.Pass):
			return []
		if isinstance(node, ast.Expr):
			if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
				return []
			if RestrictedPythonCompiler._is_super_init(node.value):
				return []
			return [*self.emit_expression(node.value), "drop"]
		if isinstance(node, ast.Assign):
			if len(node.targets) != 1:
				self.error(node, "unpacking and chained assignment are unsupported")
			return self.emit_assignment(node.targets[0], node.value)
		if isinstance(node, ast.AnnAssign):
			if node.value is None:
				self.error(node, "declarations without values are unsupported")
			return self.emit_assignment(node.target, node.value)
		if isinstance(node, ast.AugAssign):
			return self.emit_augmented_assignment(node)
		if isinstance(node, ast.If):
			lines = [*self.truthy(self.emit_expression(node.test)), "if"]
			for statement in node.body:
				lines.extend("  " + line for line in self.emit_statement(statement))
			if node.orelse:
				lines.append("else")
				for statement in node.orelse:
					lines.extend("  " + line for line in self.emit_statement(statement))
			lines.append("end")
			return lines
		if isinstance(node, ast.While):
			if node.orelse:
				self.error(node, "while-else is unsupported")
			break_label = self.new_label("break")
			loop_label = self.new_label("while")
			self.break_labels.append(break_label)
			self.continue_labels.append(loop_label)
			lines = [f"block ${break_label}", f"  loop ${loop_label}"]
			lines.extend("    " + line for line in self.truthy(self.emit_expression(node.test)))
			lines.append(f"    i32.eqz")
			lines.append(f"    br_if ${break_label}")
			for statement in node.body:
				lines.extend("    " + line for line in self.emit_statement(statement))
			lines.extend((f"    br ${loop_label}", "  end", "end"))
			self.continue_labels.pop()
			self.break_labels.pop()
			return lines
		if isinstance(node, ast.For):
			return self.emit_for(node)
		if isinstance(node, ast.Return):
			if node.value is None or self._is_controller_expression(node.value):
				return ["i64.const 0", "return"]
			return [*self.emit_expression(node.value), "return"]
		if isinstance(node, ast.Break):
			if not self.break_labels:
				self.error(node, "break outside a loop")
			return [f"br ${self.break_labels[-1]}"]
		if isinstance(node, ast.Continue):
			if not self.continue_labels:
				self.error(node, "continue outside a loop")
			return [f"br ${self.continue_labels[-1]}"]
		self.error(node, f"statement {type(node).__name__} is not supported")

	def emit_assignment(self, target: ast.AST, value: ast.AST) -> List[str]:
		value_type = self.infer_type(value)
		lines = self.emit_expression(value)
		if isinstance(target, ast.Name):
			self.local_types[target.id] = value_type
			return [*lines, f"local.set ${target.id}"]
		if RestrictedPythonCompiler._is_self_attribute(target):
			if target.attr not in self.compiler.state_values:
				self.error(target, f"state field {target.attr!r} must be declared in __init__")
			declared = self.compiler.state_types[target.attr]
			if declared == "unknown":
				self.compiler.state_types[target.attr] = value_type
			elif value_type not in {declared, "unknown"}:
				self.error(value, f"cannot assign {value_type} to state field {target.attr} ({declared})")
			return [*lines, f"global.set $state_{target.attr}"]
		self.error(target, "only local names and declared self fields can be assigned")

	def emit_augmented_assignment(self, node: ast.AugAssign) -> List[str]:
		if isinstance(node.target, ast.Name):
			load = [f"local.get ${node.target.id}"]
			store = f"local.set ${node.target.id}"
		elif RestrictedPythonCompiler._is_self_attribute(node.target):
			if node.target.attr not in self.compiler.state_values:
				self.error(node.target, "state field must be declared in __init__")
			load = [f"global.get $state_{node.target.attr}"]
			store = f"global.set $state_{node.target.attr}"
		else:
			self.error(node.target, "unsupported augmented assignment target")
		operator = self.binary_operator(node.op, node)
		return [*load, *self.emit_expression(node.value), operator, store]

	def emit_for(self, node: ast.For) -> List[str]:
		if node.orelse:
			self.error(node, "for-else is unsupported")
		if not isinstance(node.target, ast.Name):
			self.error(node.target, "loop targets must be local names")
		iterator = node.iter
		if isinstance(iterator, ast.Call) and isinstance(iterator.func, ast.Name) and iterator.func.id == "range":
			return self.emit_range_for(node, iterator)
		if self._is_direction_iterator(iterator):
			return self.emit_direction_for(node, iterator)
		if self._controller_call_name(iterator) == "sense_nearby_entities":
			return self.emit_sense_for(node, iterator)
		self.error(iterator, "for loops only support range, Direction lists, or sense_nearby_entities")

	def emit_range_for(self, node: ast.For, iterator: ast.Call) -> List[str]:
		if iterator.keywords or len(iterator.args) not in {1, 2}:
			self.error(iterator, "range supports range(stop) and range(start, stop)")
		start = ast.Constant(value=0) if len(iterator.args) == 1 else iterator.args[0]
		stop = iterator.args[-1]
		return self.emit_counted_loop(node, start, stop, "int", None)

	def emit_direction_for(self, node: ast.For, iterator: ast.Call) -> List[str]:
		if iterator.args or iterator.keywords:
			self.error(iterator, "direction iterators take no arguments")
		name = iterator.func.attr
		count = 9 if name == "all_directions" else 4
		api = "direction_all_at" if name == "all_directions" else "direction_cardinal_at"
		return self.emit_counted_loop(node, ast.Constant(value=0), ast.Constant(value=count), "direction", api)

	def emit_counted_loop(
		self,
		node: ast.For,
		start: ast.AST,
		stop: ast.AST,
		target_type: str,
		transform_api: Optional[str],
	) -> List[str]:
		index = self.new_temp("int")
		end_value = self.new_temp("int")
		break_label = self.new_label("break")
		loop_label = self.new_label("for")
		continue_label = self.new_label("continue")
		self.local_types[node.target.id] = target_type
		lines = [
			*self.emit_expression(start), f"local.set ${index}",
			*self.emit_expression(stop), f"local.set ${end_value}",
			f"block ${break_label}", f"  loop ${loop_label}",
			f"    local.get ${index}", f"    local.get ${end_value}", "    i64.lt_s", f"    i32.eqz", f"    br_if ${break_label}",
			f"    local.get ${index}",
		]
		if transform_api:
			lines.append(f"    call $api_{transform_api}")
		lines.append(f"    local.set ${node.target.id}")
		lines.append(f"    block ${continue_label}")
		self.break_labels.append(break_label)
		self.continue_labels.append(continue_label)
		for statement in node.body:
			lines.extend("      " + line for line in self.emit_statement(statement))
		self.continue_labels.pop()
		self.break_labels.pop()
		lines.extend((
			"    end",
			f"    local.get ${index}", "    i64.const 1", "    i64.add", f"    local.set ${index}",
			f"    br ${loop_label}", "  end", "end",
		))
		return lines

	def emit_sense_for(self, node: ast.For, iterator: ast.Call) -> List[str]:
		if iterator.args:
			self.error(iterator, "sense_nearby_entities only accepts keyword filters in sandbox mode")
		allowed = {"radius", "center", "teams"}
		keywords = {keyword.arg: keyword.value for keyword in iterator.keywords if keyword.arg is not None}
		if len(keywords) != len(iterator.keywords) or set(keywords) - allowed:
			self.error(iterator, "unsupported sense_nearby_entities filter")
		index = self.new_temp("int")
		end_value = self.new_temp("int")
		break_label = self.new_label("break")
		loop_label = self.new_label("sense")
		continue_label = self.new_label("continue")
		self.local_types[node.target.id] = "entity"
		lines = [
			"i64.const 0", f"local.set ${index}",
			"call $api_sense_count", f"local.set ${end_value}",
			f"block ${break_label}", f"  loop ${loop_label}",
			f"    local.get ${index}", f"    local.get ${end_value}", "    i64.lt_s", "    i32.eqz", f"    br_if ${break_label}",
			f"    local.get ${index}", f"    local.set ${node.target.id}",
			f"    block ${continue_label}",
		]
		self.break_labels.append(break_label)
		self.continue_labels.append(continue_label)
		filter_lines = self.emit_sense_filter(node.target.id, keywords)
		if filter_lines:
			lines.extend("      " + line for line in self.truthy(filter_lines))
			lines.append("      if")
			for statement in node.body:
				lines.extend("        " + line for line in self.emit_statement(statement))
			lines.append("      end")
		else:
			for statement in node.body:
				lines.extend("      " + line for line in self.emit_statement(statement))
		self.continue_labels.pop()
		self.break_labels.pop()
		lines.extend((
			"    end",
			f"    local.get ${index}", "    i64.const 1", "    i64.add", f"    local.set ${index}",
			f"    br ${loop_label}", "  end", "end",
		))
		return lines

	def emit_sense_filter(self, entity_name: str, keywords: Dict[str, ast.AST]) -> List[str]:
		conditions: List[List[str]] = []
		if "radius" in keywords:
			center = keywords.get("center")
			center_lines = self.emit_expression(center) if center is not None else ["call $api_get_location"]
			conditions.append([
				f"local.get ${entity_name}", "call $api_sense_location",
				*center_lines, "call $api_location_distance_to",
				*self.emit_expression(keywords["radius"]), "i64.le_s", "i64.extend_i32_u",
			])
		elif "center" in keywords:
			self.error(keywords["center"], "center requires an explicit radius")
		if "teams" in keywords:
			teams = keywords["teams"]
			if self._controller_call_name(teams) == "get_opponent":
				conditions.append([
					f"local.get ${entity_name}", "call $api_sense_team", "i64.const 0", "i64.ge_s", "i64.extend_i32_u",
					f"local.get ${entity_name}", "call $api_sense_team", "call $api_is_opponent", "i64.and",
				])
			elif isinstance(teams, (ast.List, ast.Tuple)) and teams.elts:
				team_condition: List[str] = []
				for index, item in enumerate(teams.elts):
					team_condition.extend((f"local.get ${entity_name}", "call $api_sense_team"))
					team_condition.extend(self.emit_expression(item))
					team_condition.extend(("i64.eq", "i64.extend_i32_u"))
					if index:
						team_condition.append("i64.or")
				conditions.append(team_condition)
			else:
				self.error(teams, "teams must be get_opponent() or a non-empty literal list")
		if not conditions:
			return []
		lines = conditions[0]
		for condition in conditions[1:]:
			lines.extend(condition)
			lines.append("i64.and")
		return lines

	def emit_expression(self, node: ast.AST) -> List[str]:
		if isinstance(node, ast.Constant):
			if node.value is None:
				return [f"i64.const {NONE_SENTINEL}"]
			if isinstance(node.value, bool):
				return [f"i64.const {int(node.value)}"]
			if isinstance(node.value, int):
				return [f"i64.const {RestrictedPythonCompiler._check_i64(node.value, node)}"]
			if isinstance(node.value, str):
				if node.value in ENTITY_TYPES:
					return [f"i64.const {ENTITY_TYPES[node.value]}"]
				if node.value == "Neutral":
					return ["i64.const -1"]
				if node.value.lstrip("-").isdigit():
					return [f"i64.const {int(node.value)}"]
				self.error(node, "only entity type and team tag strings are supported")
			self.error(node, "floats, bytes, and complex constants are unsupported")
		if isinstance(node, ast.Name):
			if node.id in self.local_types and self.local_types[node.id] == "controller":
				self.error(node, "controller is only valid as an API call receiver")
			if node.id in self.local_types:
				return [f"local.get ${node.id}"]
			if node.id in {"True", "False", "None"}:
				return [f"i64.const {1 if node.id == 'True' else 0}"]
			if node.id.upper() in {name.upper() for name in ENTITY_TYPES}:
				return [f"i64.const {ENTITY_TYPES[node.id.lower()]}"]
			if node.id.upper() in {name.upper() for name in DIRECTIONS}:
				return [f"i64.const {DIRECTIONS[node.id.lower()]}"]
			self.error(node, f"unknown local {node.id!r}")
		if isinstance(node, ast.Attribute):
			return self.emit_attribute(node)
		if isinstance(node, ast.Call):
			return self.emit_call(node)
		if isinstance(node, ast.BinOp):
			return [*self.emit_expression(node.left), *self.emit_expression(node.right), self.binary_operator(node.op, node)]
		if isinstance(node, ast.UnaryOp):
			if isinstance(node.op, ast.Not):
				return [*self.emit_expression(node.operand), "i64.eqz", "i64.extend_i32_u"]
			if isinstance(node.op, ast.USub):
				return ["i64.const 0", *self.emit_expression(node.operand), "i64.sub"]
			if isinstance(node.op, ast.UAdd):
				return self.emit_expression(node.operand)
			if isinstance(node.op, ast.Invert):
				return [*self.emit_expression(node.operand), "i64.const -1", "i64.xor"]
			self.error(node, "unsupported unary operator")
		if isinstance(node, ast.BoolOp):
			return self.emit_boolean(node)
		if isinstance(node, ast.Compare):
			if len(node.ops) != 1 or len(node.comparators) != 1:
				self.error(node, "chained comparisons are unsupported")
			operator = self.compare_operator(node.ops[0], node)
			return [*self.emit_expression(node.left), *self.emit_expression(node.comparators[0]), operator, "i64.extend_i32_u"]
		if isinstance(node, ast.IfExp):
			return [
				*self.truthy(self.emit_expression(node.test)), "if (result i64)",
				*('  ' + line for line in self.emit_expression(node.body)), "else",
				*('  ' + line for line in self.emit_expression(node.orelse)), "end",
			]
		self.error(node, f"expression {type(node).__name__} is not supported")

	def emit_attribute(self, node: ast.Attribute) -> List[str]:
		if RestrictedPythonCompiler._is_self_attribute(node):
			if node.attr == "controller":
				self.error(node, "controller is only valid as an API call receiver")
			if node.attr not in self.compiler.state_values:
				self.error(node, f"undeclared state field {node.attr!r}")
			return [f"global.get $state_{node.attr}"]
		base_type = self.infer_type(node.value)
		if base_type == "entity":
			mapping = {
				"ID": "sense_id", "energy": "sense_energy", "defence": "sense_defence",
				"location": "sense_location", "team": "sense_team", "type": "sense_type", "radio": "sense_radio",
			}
			if node.attr not in mapping:
				self.error(node, f"unknown EntityInfo field {node.attr!r}")
			return [*self.emit_expression(node.value), f"call $api_{mapping[node.attr]}"]
		if base_type == "location" and node.attr in {"x", "y"}:
			return [*self.emit_expression(node.value), f"call $api_location_{node.attr}"]
		if base_type == "direction" and node.attr in {"dx", "dy"}:
			return [*self.emit_expression(node.value), f"call $api_direction_{node.attr}"]
		if base_type in {"entity_type", "team"} and node.attr in {"name", "tag"}:
			return self.emit_expression(node.value)
		if base_type == "entity_type":
			mapping = {
				"action_radius": "type_action_radius",
				"detection_radius": "type_detection_radius",
				"initial_cooldown": "type_initial_cooldown",
				"sensor_radius": "type_sensor_radius",
			}
			if node.attr in mapping:
				return [*self.emit_expression(node.value), f"call $api_{mapping[node.attr]}"]
		self.error(node, f"attribute {node.attr!r} is not available for {base_type}")

	def emit_call(self, node: ast.Call) -> List[str]:
		controller_method = self._controller_call_name(node)
		if controller_method is not None:
			return self.emit_controller_call(node, controller_method)
		if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
			if node.keywords:
				self.error(node, "helper calls do not support keyword arguments")
			if node.func.attr not in self.compiler.methods:
				self.error(node, f"unknown helper method {node.func.attr!r}")
			return [*(line for arg in node.args for line in self.emit_expression(arg)), f"call $fn_{node.func.attr}"]
		if isinstance(node.func, ast.Name):
			return self.emit_builtin_or_constructor(node)
		if isinstance(node.func, ast.Attribute):
			if (
				isinstance(node.func.value, ast.Name)
				and node.func.value.id == "Direction"
				and node.func.attr in DIRECTIONS
				and not node.args and not node.keywords
			):
				return [f"i64.const {DIRECTIONS[node.func.attr]}"]
			return self.emit_value_method(node)
		self.error(node, "dynamic calls are forbidden")

	def emit_controller_call(self, node: ast.Call, method: str) -> List[str]:
		if method in {"sense_nearby_entities", "get_opponent", "get_all_teams"}:
			self.error(node, f"{method} is only valid as a loop/filter expression")
		if method in {"can_analyze", "analyze"}:
			if node.keywords or len(node.args) != 1:
				self.error(node, f"{method} requires one positional target")
			target_type = self.infer_type(node.args[0])
			suffix = "location" if target_type == "location" else "id"
			return [*self.emit_expression(node.args[0]), f"call $api_{method}_{suffix}"]
		if method == "adjacent_location":
			if node.keywords or len(node.args) != 1:
				self.error(node, "adjacent_location requires one direction")
			return ["call $api_get_location", *self.emit_expression(node.args[0]), "call $api_location_add"]
		if method not in CONTROLLER_METHODS:
			self.error(node, f"Controller method {method!r} is not available in sandbox mode")
		api_name, _ = CONTROLLER_METHODS[method]
		spec = next(spec for spec in HOST_IMPORTS if spec.name == api_name)
		if node.keywords or len(node.args) != spec.params:
			self.error(node, f"{method} requires {spec.params} positional arguments")
		return [*(line for arg in node.args for line in self.emit_expression(arg)), f"call $api_{api_name}"]

	def emit_builtin_or_constructor(self, node: ast.Call) -> List[str]:
		name = node.func.id
		if node.keywords:
			self.error(node, "keyword arguments are unsupported here")
		if name == "EntityType" and len(node.args) == 1:
			return self.emit_expression(node.args[0])
		if name == "Team" and len(node.args) == 1:
			return self.emit_expression(node.args[0])
		if name == "Direction" and len(node.args) == 2:
			return [*self.emit_expression(node.args[0]), *self.emit_expression(node.args[1]), "call $api_direction_make"]
		if name == "MapLocation" and len(node.args) == 2:
			return [*self.emit_expression(node.args[0]), *self.emit_expression(node.args[1]), "call $api_location_make"]
		if name in {"int", "bool"} and len(node.args) == 1:
			if name == "bool":
				return [*self.emit_expression(node.args[0]), "i64.const 0", "i64.ne", "i64.extend_i32_u"]
			return self.emit_expression(node.args[0])
		if name == "len" and len(node.args) == 1 and self._controller_call_name(node.args[0]) == "sense_nearby_entities":
			return ["call $api_sense_count"]
		if name in {"min", "max"} and len(node.args) == 2:
			left = self.new_temp()
			right = self.new_temp()
			comparison = "i64.lt_s" if name == "min" else "i64.gt_s"
			return [
				*self.emit_expression(node.args[0]), f"local.set ${left}",
				*self.emit_expression(node.args[1]), f"local.set ${right}",
				f"local.get ${left}", f"local.get ${right}", comparison,
				"if (result i64)", f"  local.get ${left}", "else", f"  local.get ${right}", "end",
			]
		if name == "abs" and len(node.args) == 1:
			value = self.new_temp()
			return [
				*self.emit_expression(node.args[0]), f"local.set ${value}",
				f"local.get ${value}", "i64.const 0", "i64.lt_s", "if (result i64)",
				"  i64.const 0", f"  local.get ${value}", "  i64.sub", "else", f"  local.get ${value}", "end",
			]
		self.error(node, f"builtin or constructor {name!r} is not supported")

	def emit_value_method(self, node: ast.Call) -> List[str]:
		if node.keywords:
			self.error(node, "value methods do not accept keyword arguments")
		base = node.func.value
		method = node.func.attr
		base_type = self.infer_type(base)
		if base_type == "location":
			mapping = {
				"add": ("location_add", 1, "location"),
				"subtract": ("location_subtract", 1, "location"),
				"translate": ("location_translate", 2, "location"),
				"direction_to": ("location_direction_to", 1, "direction"),
				"distance_to": ("location_distance_to", 1, "int"),
				"is_adjacent_to": ("location_is_adjacent_to", 1, "bool"),
				"equals": (None, 1, "bool"),
			}
		elif base_type == "direction":
			mapping = {
				"get_dx": ("direction_dx", 0, "int"),
				"get_dy": ("direction_dy", 0, "int"),
				"opposite": ("direction_opposite", 0, "direction"),
				"rotate_left": ("direction_rotate_left", 0, "direction"),
				"rotate_right": ("direction_rotate_right", 0, "direction"),
				"equals": (None, 1, "bool"),
			}
		elif base_type in {"team", "entity_type"}:
			if method == "is_player" and base_type == "team" and not node.args:
				return [*self.emit_expression(base), "i64.const 0", "i64.ge_s", "i64.extend_i32_u"]
			mapping = {"equals": (None, 1, "bool")}
		else:
			self.error(node, f"method {method!r} is not available for {base_type}")
		if method not in mapping:
			self.error(node, f"method {method!r} is not available for {base_type}")
		api_name, arity, _ = mapping[method]
		if len(node.args) != arity:
			self.error(node, f"{method} requires {arity} arguments")
		if api_name is None:
			return [*self.emit_expression(base), *self.emit_expression(node.args[0]), "i64.eq", "i64.extend_i32_u"]
		return [*self.emit_expression(base), *(line for arg in node.args for line in self.emit_expression(arg)), f"call $api_{api_name}"]

	def emit_boolean(self, node: ast.BoolOp) -> List[str]:
		if not node.values:
			return ["i64.const 0"]
		lines = self.emit_expression(node.values[0])
		for value in node.values[1:]:
			if isinstance(node.op, ast.And):
				lines = [*self.truthy(lines), "if (result i64)", *('  ' + line for line in self.emit_expression(value)), "else", "  i64.const 0", "end"]
			else:
				lines = [*self.truthy(lines), "if (result i64)", "  i64.const 1", "else", *('  ' + line for line in self.emit_expression(value)), "end"]
		return lines

	def binary_operator(self, operator: ast.operator, node: ast.AST) -> str:
		mapping = {
			ast.Add: "i64.add", ast.Sub: "i64.sub", ast.Mult: "i64.mul",
			ast.FloorDiv: "i64.div_s", ast.Mod: "i64.rem_s",
			ast.BitAnd: "i64.and", ast.BitOr: "i64.or", ast.BitXor: "i64.xor",
			ast.LShift: "i64.shl", ast.RShift: "i64.shr_s",
		}
		for kind, instruction in mapping.items():
			if isinstance(operator, kind):
				return instruction
		self.error(node, "operator is unsupported; sandbox integers are signed i64")

	def compare_operator(self, operator: ast.cmpop, node: ast.AST) -> str:
		mapping = {
			ast.Eq: "i64.eq", ast.NotEq: "i64.ne", ast.Is: "i64.eq", ast.IsNot: "i64.ne",
			ast.Lt: "i64.lt_s", ast.LtE: "i64.le_s", ast.Gt: "i64.gt_s", ast.GtE: "i64.ge_s",
		}
		for kind, instruction in mapping.items():
			if isinstance(operator, kind):
				return instruction
		self.error(node, "membership and identity comparisons are unsupported")

	def infer_type(self, node: ast.AST) -> str:
		if isinstance(node, ast.Constant):
			if isinstance(node.value, bool):
				return "bool"
			if node.value is None:
				return "unknown"
			if isinstance(node.value, int):
				return "int"
			if isinstance(node.value, str):
				if node.value in ENTITY_TYPES:
					return "entity_type"
				return "team"
		if isinstance(node, ast.Name):
			return self.local_types.get(node.id, "int")
		if RestrictedPythonCompiler._is_self_attribute(node):
			return self.compiler.state_types.get(node.attr, "unknown")
		if isinstance(node, ast.Attribute):
			base_type = self.infer_type(node.value)
			if base_type == "entity":
				return {"location": "location", "team": "team", "type": "entity_type"}.get(node.attr, "int")
			if base_type == "location" and node.attr in {"x", "y"}:
				return "int"
			if base_type == "direction" and node.attr in {"dx", "dy"}:
				return "int"
			if base_type == "entity_type" and node.attr == "name":
				return "entity_type"
			if base_type == "team" and node.attr == "tag":
				return "team"
			return "int"
		if isinstance(node, ast.Call):
			method = self._controller_call_name(node)
			if method in CONTROLLER_METHODS:
				return CONTROLLER_METHODS[method][1]
			if method in {"can_analyze"}:
				return "bool"
			if method in {"analyze", "adjacent_location"}:
				return "location" if method == "adjacent_location" else "int"
			if isinstance(node.func, ast.Name):
				return {"EntityType": "entity_type", "Team": "team", "Direction": "direction", "MapLocation": "location", "bool": "bool"}.get(node.func.id, "int")
			if isinstance(node.func, ast.Attribute):
				if isinstance(node.func.value, ast.Name) and node.func.value.id == "Direction" and node.func.attr in DIRECTIONS:
					return "direction"
				base_type = self.infer_type(node.func.value)
				if base_type == "location":
					return {"add": "location", "subtract": "location", "translate": "location", "direction_to": "direction", "is_adjacent_to": "bool"}.get(node.func.attr, "int")
				if base_type == "direction":
					return "direction" if node.func.attr in {"opposite", "rotate_left", "rotate_right"} else "int"
			return "int"
		if isinstance(node, (ast.Compare, ast.BoolOp)):
			return "bool"
		if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
			return "bool"
		if isinstance(node, ast.IfExp):
			return self.infer_type(node.body)
		return "int"

	@staticmethod
	def _is_controller_expression(node: ast.AST) -> bool:
		return (
			isinstance(node, ast.Name) and node.id in {"controller", "api"}
		) or (
			isinstance(node, ast.Attribute)
			and isinstance(node.value, ast.Name)
			and node.value.id == "self"
			and node.attr == "controller"
		)

	def _controller_call_name(self, node: ast.AST) -> Optional[str]:
		if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
			return None
		if self._is_controller_expression(node.func.value):
			return node.func.attr
		return None

	@staticmethod
	def _is_direction_iterator(node: ast.AST) -> bool:
		return (
			isinstance(node, ast.Call)
			and isinstance(node.func, ast.Attribute)
			and isinstance(node.func.value, ast.Name)
			and node.func.value.id == "Direction"
			and node.func.attr in {"all_directions", "cardinal_directions"}
		)


def compile_restricted_python(source: str, filename: str = "<player>", **limits) -> str:
	return RestrictedPythonCompiler(source, filename, **limits).compile()

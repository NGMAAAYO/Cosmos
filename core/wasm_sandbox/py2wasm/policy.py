"""Positive source policy shared by the future py2wasm competition backend."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict


TEAM_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
ALLOWED_EXTERNAL_MODULES = {
	"__future__",
	"dataclasses",
	"heapq",
	"math",
	"random",
	"types",
	"core",
	"core.api",
	"core.entity",
	"src",
	"src.template",
}
BANNED_NAMES = {
	"__import__",
	"__builtins__",
	"breakpoint",
	"compile",
	"delattr",
	"dir",
	"eval",
	"exec",
	"getattr",
	"globals",
	"help",
	"input",
	"locals",
	"memoryview",
	"open",
	"setattr",
	"vars",
}
BANNED_ATTRIBUTES = {
	"__base__",
	"__bases__",
	"__builtins__",
	"__class__",
	"__closure__",
	"__code__",
	"__dict__",
	"__getattribute__",
	"__globals__",
	"__mro__",
	"__loader__",
	"__package__",
	"__reduce__",
	"__reduce_ex__",
	"__subclasses__",
	"__spec__",
	"__traceback__",
	"_call",
	"_index",
	"_raw_call",
	"_raw_call_float",
	"cr_frame",
	"f_back",
	"f_builtins",
	"f_code",
	"f_globals",
	"f_locals",
	"gi_frame",
	"tb_frame",
	"tb_next",
	"mro",
	"with_traceback",
}


class PlayerPolicyError(ValueError):
	pass


def _resolve_import(module_path: str, node: ast.ImportFrom) -> str:
	if not node.level:
		return node.module or ""
	package = module_path.split(".")[:-1]
	remove = node.level - 1
	if remove > len(package):
		return ""
	base = package[:len(package) - remove] if remove else package
	if node.module:
		base.extend(node.module.split("."))
	return ".".join(base)


def _ast_depth(tree: ast.AST) -> int:
	maximum = 0
	stack = [(tree, 1)]
	while stack:
		node, depth = stack.pop()
		maximum = max(maximum, depth)
		stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
	return maximum


def validate_team_sources(
	team: str,
	player_root: str | Path = "src",
	*,
	max_source_bytes: int = 512 * 1024,
	max_ast_nodes: int = 200_000,
	max_ast_depth: int = 120,
) -> Dict[str, bytes]:
	"""Read and validate every Python file in one team package.

	Module and class globals remain legal because each entity will receive a
	separate Wasm Store/Instance.  The policy instead prevents reflection and
	host-capability discovery, while allowing all Python constructs currently
	used by the checked-in strategies.
	"""

	if not TEAM_NAME.fullmatch(team):
		raise PlayerPolicyError(f"invalid team name {team!r}")
	root = Path(player_root).resolve()
	team_candidate = root.joinpath(team)
	if team_candidate.is_symlink():
		raise PlayerPolicyError(f"team directory cannot be a symlink: {team_candidate}")
	team_dir = team_candidate.resolve()
	if team_dir.parent != root or not team_dir.is_dir():
		raise PlayerPolicyError(f"team directory does not exist: {team_dir}")

	result: Dict[str, bytes] = {}
	total_bytes = 0
	total_nodes = 0
	team_prefix = f"src.{team}"
	for filename in sorted(team_dir.rglob("*.py")):
		if not filename.is_file():
			continue
		resolved = filename.resolve()
		if filename.is_symlink() or team_dir not in resolved.parents:
			raise PlayerPolicyError(f"player source escapes team directory: {filename}")
		relative = filename.relative_to(root).as_posix()
		module_path = "src." + relative[:-3].replace("/", ".")
		if module_path.endswith(".__init__"):
			module_path = module_path[:-9]
		try:
			data = filename.read_bytes()
			source = data.decode("utf-8")
		except (OSError, UnicodeError) as exc:
			raise PlayerPolicyError(f"cannot read {filename}: {exc}") from exc
		total_bytes += len(data)
		if total_bytes > max_source_bytes:
			raise PlayerPolicyError(f"team source exceeds {max_source_bytes} bytes")
		try:
			tree = ast.parse(source, filename=str(filename))
		except SyntaxError as exc:
			raise PlayerPolicyError(str(exc)) from exc
		nodes = list(ast.walk(tree))
		total_nodes += len(nodes)
		if total_nodes > max_ast_nodes:
			raise PlayerPolicyError(f"team AST exceeds {max_ast_nodes} nodes")
		if _ast_depth(tree) > max_ast_depth:
			raise PlayerPolicyError(f"{filename}: AST nesting exceeds {max_ast_depth}")

		for node in nodes:
			if isinstance(node, ast.Import):
				modules = [item.name for item in node.names]
			elif isinstance(node, ast.ImportFrom):
				imported_module = _resolve_import(module_path, node)
				modules = [imported_module]
				if not imported_module.startswith(team_prefix + "."):
					for item in node.names:
						if item.name != "*" and item.name.startswith("_"):
							raise PlayerPolicyError(
								f"{filename}:{node.lineno}: private imports are unavailable"
							)
			else:
				modules = []
			for imported in modules:
				if imported in ALLOWED_EXTERNAL_MODULES or imported.startswith(team_prefix + "."):
					continue
				raise PlayerPolicyError(
					f"{filename}:{node.lineno}: import {imported!r} is outside the player whitelist"
				)
			if isinstance(node, ast.Name) and node.id in BANNED_NAMES:
				raise PlayerPolicyError(
					f"{filename}:{node.lineno}: name {node.id!r} is unavailable in the sandbox"
				)
			if isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRIBUTES:
				raise PlayerPolicyError(
					f"{filename}:{node.lineno}: reflective attribute {node.attr!r} is unavailable"
				)
		result[relative] = data

	if f"{team}/main.py" not in result:
		raise PlayerPolicyError(f"team {team!r} has no main.py")
	return result

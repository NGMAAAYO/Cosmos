"""Pinned adapter for wasmerio/py2wasm's Nuitka/WASI compiler."""

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .policy import validate_team_sources


PY2WASM_COMMIT = "07da21cac92f5e5967c4bb5d39aaabaee1c70b3e"
PATCH_MARKER = "The host Python's MODLIBS describe native linking."
BRIDGE_MARKER = "PY2WASM_COSMOS"
EXPORT_PATCH_MARKER = 'not os.environ.get("PY2WASM_COSMOS")'
BRIDGE_ABI = "cosmos-py2wasm-v3"
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_INITIAL_MEMORY_PAGES = 256
COMPILE_TIMEOUT_SECONDS = 600
ALLOWED_WASI_IMPORTS = {
	"args_get", "args_sizes_get", "environ_get", "environ_sizes_get",
	"clock_res_get", "clock_time_get", "fd_advise", "fd_close", "fd_datasync",
	"fd_fdstat_get", "fd_fdstat_set_flags", "fd_filestat_get",
	"fd_filestat_set_size", "fd_filestat_set_times", "fd_pread", "fd_prestat_get",
	"fd_prestat_dir_name", "fd_pwrite", "fd_read", "fd_readdir", "fd_seek",
	"fd_sync", "fd_tell", "fd_write", "path_create_directory", "path_filestat_get",
	"path_filestat_set_times", "path_link", "path_open", "path_readlink",
	"path_remove_directory", "path_rename", "path_symlink", "path_unlink_file",
	"poll_oneoff", "proc_exit", "sched_yield", "random_get", "sock_accept",
	"sock_recv", "sock_send", "sock_shutdown",
}
REQUIRED_COSMOS_IMPORTS = {"call", "call_float"}
SAFE_MODULES = {
	"dataclasses": "_cosmos_dataclasses",
	"random": "_cosmos_random",
	"types": "_cosmos_types",
}


class Py2WasmCompileError(RuntimeError):
	pass


class Py2WasmUnavailableError(Py2WasmCompileError):
	pass


@dataclass(frozen=True)
class Py2WasmArtifact:
	binary: bytes
	digest: str
	imports: Tuple[str, ...]
	exports: Tuple[str, ...]
	initial_memory_pages: int


class _WasmReader:
	def __init__(self, data: bytes) -> None:
		self.data = data
		self.offset = 0

	def byte(self) -> int:
		if self.offset >= len(self.data):
			raise Py2WasmCompileError("truncated WebAssembly binary")
		value = self.data[self.offset]
		self.offset += 1
		return value

	def uleb(self, maximum_bits: int = 32) -> int:
		value = 0
		shift = 0
		while shift < maximum_bits + 7:
			byte = self.byte()
			value |= (byte & 0x7f) << shift
			if not byte & 0x80:
				if value >= 1 << maximum_bits:
					raise Py2WasmCompileError("oversized WebAssembly integer")
				return value
			shift += 7
		raise Py2WasmCompileError("invalid WebAssembly integer")

	def name(self) -> str:
		length = self.uleb()
		end = self.offset + length
		if end > len(self.data):
			raise Py2WasmCompileError("truncated WebAssembly name")
		try:
			value = self.data[self.offset:end].decode("utf-8")
		except UnicodeDecodeError as exc:
			raise Py2WasmCompileError("invalid UTF-8 in WebAssembly name") from exc
		self.offset = end
		return value

	def limits(self) -> tuple[int, Optional[int]]:
		flags = self.uleb()
		if flags & ~0x7:
			raise Py2WasmCompileError("unsupported WebAssembly memory limits")
		bits = 64 if flags & 0x4 else 32
		minimum = self.uleb(bits)
		maximum = self.uleb(bits) if flags & 0x1 else None
		return minimum, maximum

	def section(self, size: int) -> "_WasmReader":
		end = self.offset + size
		if end > len(self.data):
			raise Py2WasmCompileError("truncated WebAssembly section")
		result = _WasmReader(self.data[self.offset:end])
		self.offset = end
		return result

	def finish(self) -> None:
		if self.offset != len(self.data):
			raise Py2WasmCompileError("malformed WebAssembly section")


def _inspect_wasm(binary: bytes):
	if not binary.startswith(b"\x00asm\x01\x00\x00\x00"):
		raise Py2WasmCompileError("py2wasm output is not a WebAssembly 1 binary")
	reader = _WasmReader(binary)
	reader.offset = 8
	imports = []
	exports = []
	memory_minimum = None
	while reader.offset < len(binary):
		section_id = reader.byte()
		section = reader.section(reader.uleb())
		if section_id not in (2, 5, 7):
			continue
		if section_id == 2:
			for _ in range(section.uleb()):
				module = section.name()
				name = section.name()
				kind = section.byte()
				imports.append((module, name, kind))
				if kind == 0:
					section.uleb()
				elif kind == 1:
					section.byte()
					section.limits()
				elif kind == 2:
					section.limits()
				elif kind == 3:
					section.byte()
					section.byte()
				elif kind == 4:
					section.byte()
					section.uleb()
				else:
					raise Py2WasmCompileError("unknown WebAssembly import kind")
		elif section_id == 5:
			count = section.uleb()
			if count != 1:
				raise Py2WasmCompileError("py2wasm artifact must define one memory")
			memory_minimum, _ = section.limits()
		elif section_id == 7:
			for _ in range(section.uleb()):
				exports.append((section.name(), section.byte(), section.uleb()))
		section.finish()
	reader.finish()
	return imports, exports, memory_minimum


def _configured_path(explicit: Optional[str], variable: str) -> Optional[Path]:
	value = explicit or os.environ.get(variable)
	if not value:
		return None
	# Preserve virtualenv Python symlinks; resolving them loses site-packages.
	return Path(os.path.abspath(os.path.expanduser(value)))


class _SafeImportRewriter(ast.NodeTransformer):
	def visit_Import(self, node: ast.Import):
		for item in node.names:
			if item.name in SAFE_MODULES:
				original = item.name
				item.name = SAFE_MODULES[original]
				item.asname = item.asname or original
		return node

	def visit_ImportFrom(self, node: ast.ImportFrom):
		if node.level == 0 and node.module in SAFE_MODULES:
			node.module = SAFE_MODULES[node.module]
		return node


def _rewrite_safe_imports(data: bytes, filename: str) -> bytes:
	tree = ast.parse(data.decode("utf-8"), filename=filename)
	tree = _SafeImportRewriter().visit(tree)
	ast.fix_missing_locations(tree)
	return (ast.unparse(tree) + "\n").encode("utf-8")


class Py2WasmCompiler:
	"""Compile approved team packages into persistent Cosmos/WASI modules."""

	def __init__(
		self,
		toolchain_root: Optional[str] = None,
		python_executable: Optional[str] = None,
		cache_root: Optional[str] = None,
	) -> None:
		self.root = _configured_path(toolchain_root, "COSMOS_PY2WASM_ROOT")
		self.python = _configured_path(python_executable, "COSMOS_PY2WASM_PYTHON")
		cache = cache_root or os.environ.get("COSMOS_PY2WASM_CACHE")
		self.cache_root = Path(cache).absolute() if cache else Path.cwd().joinpath(
			".cache", "cosmos-py2wasm-artifacts",
		)
		if self.root is None or self.python is None:
			raise Py2WasmUnavailableError(
				"set COSMOS_PY2WASM_ROOT and COSMOS_PY2WASM_PYTHON; "
				"tools/setup_py2wasm.py prepares a pinned toolchain"
			)
		self._verify_toolchain()

	def _verify_toolchain(self) -> None:
		entry = self.root.joinpath("bin", "py2wasm")
		patched = self.root.joinpath("nuitka", "PythonVersions.py")
		bridge = self.root.joinpath("nuitka", "build", "static_src", "CosmosModule.c")
		backend = self.root.joinpath("nuitka", "build", "Backend.scons")
		main = self.root.joinpath("nuitka", "__main__.py")
		if not all(path.is_file() for path in (entry, patched, bridge, backend, main, self.python)):
			raise Py2WasmUnavailableError("py2wasm toolchain is incomplete")
		try:
			head = subprocess.run(
				["git", "-C", str(self.root), "rev-parse", "HEAD"],
				check=True, capture_output=True, text=True, timeout=10,
			).stdout.strip()
		except (OSError, subprocess.SubprocessError) as exc:
			raise Py2WasmUnavailableError(f"cannot verify py2wasm checkout: {exc}") from exc
		if head != PY2WASM_COMMIT:
			raise Py2WasmUnavailableError(f"py2wasm commit must be {PY2WASM_COMMIT}, got {head}")
		if PATCH_MARKER not in patched.read_text(encoding="utf-8"):
			raise Py2WasmUnavailableError("the required WASI link-library patch is not applied")
		if BRIDGE_MARKER not in main.read_text(encoding="utf-8"):
			raise Py2WasmUnavailableError("the required Cosmos runtime patch is not applied")
		if EXPORT_PATCH_MARKER not in backend.read_text(encoding="utf-8"):
			raise Py2WasmUnavailableError("the required Cosmos export-surface patch is not applied")
		check = subprocess.run(
			[str(self.python), "-I", "-c", "import sys;print(sys.version_info[:2])"],
			check=False, capture_output=True, text=True, timeout=10,
		)
		if check.returncode or check.stdout.strip() != "(3, 11)":
			raise Py2WasmUnavailableError("py2wasm requires a Python 3.11 compiler environment")

	def compile_team(self, team: str, player_root: str | Path = "src") -> Py2WasmArtifact:
		files = validate_team_sources(team, player_root)
		guest_root = Path(__file__).parents[1].joinpath("guest")
		guest_files = (
			*sorted(guest_root.joinpath("core").glob("*.py")),
			guest_root.joinpath("src", "template.py"),
			guest_root.joinpath("dataclasses.py"),
			guest_root.joinpath("random.py"),
			guest_root.joinpath("types.py"),
			guest_root.joinpath("_cosmos_compat.py"),
		)
		key = hashlib.sha256()
		key.update(f"{PY2WASM_COMMIT}:{BRIDGE_ABI}:{sys.version_info[:2]}".encode("ascii"))
		for relative, data in sorted(files.items()):
			key.update(relative.encode("utf-8") + b"\0" + data + b"\0")
		for source in guest_files:
			key.update(source.name.encode("utf-8") + b"\0" + source.read_bytes() + b"\0")
		cache_path = self.cache_root.joinpath(key.hexdigest() + ".wasm")
		try:
			cached = cache_path.read_bytes()
			return self.inspect(cached)
		except (OSError, Py2WasmCompileError):
			pass
		with tempfile.TemporaryDirectory(prefix="cosmos-py2wasm-") as temporary:
			stage = Path(temporary)
			for relative, data in files.items():
				target = stage.joinpath("src", team, Path(relative).relative_to(team))
				target.parent.mkdir(parents=True, exist_ok=True)
				target.write_bytes(_rewrite_safe_imports(data, relative))
			for package in ("core", "src"):
				target_dir = stage.joinpath(package)
				target_dir.mkdir(parents=True, exist_ok=True)
				target_dir.joinpath("__init__.py").write_text("", encoding="utf-8")
			for source in guest_root.joinpath("core").glob("*.py"):
				shutil.copy2(source, stage.joinpath("core", source.name))
			shutil.copy2(guest_root.joinpath("src", "template.py"), stage.joinpath("src", "template.py"))
			shutil.copy2(
				guest_root.joinpath("dataclasses.py"), stage.joinpath("_cosmos_dataclasses.py"),
			)
			shutil.copy2(guest_root.joinpath("random.py"), stage.joinpath("_cosmos_random.py"))
			shutil.copy2(guest_root.joinpath("types.py"), stage.joinpath("_cosmos_types.py"))
			shutil.copy2(guest_root.joinpath("_cosmos_compat.py"), stage.joinpath("_cosmos_compat.py"))
			stage.joinpath("entry.py").write_text(
				"import builtins\n"
				"from _cosmos_compat import classmethod, property, staticmethod\n"
				"builtins.classmethod = classmethod\n"
				"builtins.property = property\n"
				"builtins.staticmethod = staticmethod\n"
				"from core.api import Controller\n"
				f"from src.{team}.main import Player\n"
				"__cosmos_controller = Controller()\n"
				"__cosmos_player = Player()\n"
				"def __cosmos_turn():\n"
				"    __cosmos_controller._begin_turn()\n"
				"    return __cosmos_player.run(__cosmos_controller)\n",
				encoding="utf-8",
			)
			output = stage.joinpath("player.wasm")
			environment = os.environ.copy()
			environment["PYTHONHASHSEED"] = "0"
			environment["PY2WASM_BUILD_DIR"] = str(stage.joinpath("build"))
			try:
				result = subprocess.run(
					[
						str(self.python), str(self.root.joinpath("bin", "py2wasm")),
						str(stage.joinpath("entry.py")), "-o", str(output),
					],
					cwd=self.root, env=environment, check=False,
					capture_output=True, text=True, timeout=COMPILE_TIMEOUT_SECONDS,
				)
			except subprocess.TimeoutExpired as exc:
				raise Py2WasmCompileError("py2wasm compilation exceeded 600 seconds") from exc
			if result.returncode:
				diagnostic = (result.stderr or result.stdout).strip()
				raise Py2WasmCompileError(f"py2wasm compilation failed: {diagnostic}")
			try:
				binary = output.read_bytes()
			except OSError as exc:
				raise Py2WasmCompileError(f"py2wasm produced no artifact: {exc}") from exc
		if len(binary) > MAX_ARTIFACT_BYTES:
			raise Py2WasmCompileError(f"py2wasm artifact exceeds {MAX_ARTIFACT_BYTES} bytes")
		if not binary.startswith(b"\x00asm"):
			raise Py2WasmCompileError("py2wasm output is not a WebAssembly binary")
		artifact = self.inspect(binary)
		try:
			self.cache_root.mkdir(parents=True, exist_ok=True)
			temporary_cache = cache_path.with_name(
				f".{cache_path.name}.{os.getpid()}.{id(binary)}.tmp",
			)
			temporary_cache.write_bytes(binary)
			os.replace(temporary_cache, cache_path)
		except OSError:
			pass
		return artifact

	@staticmethod
	def inspect(binary: bytes) -> Py2WasmArtifact:
		parsed_imports, parsed_exports, pages = _inspect_wasm(binary)
		imports = tuple(f"{module}.{name}" for module, name, _ in parsed_imports)
		cosmos_imports = set()
		for module, name, kind in parsed_imports:
			if kind != 0:
				raise Py2WasmCompileError(f"unexpected non-function import {module}.{name}")
			if module == "cosmos" and name in REQUIRED_COSMOS_IMPORTS:
				cosmos_imports.add(name)
				continue
			if module != "wasi_snapshot_preview1" or name not in ALLOWED_WASI_IMPORTS:
				raise Py2WasmCompileError(f"unexpected Wasm import {module}.{name}")
		if cosmos_imports != REQUIRED_COSMOS_IMPORTS:
			raise Py2WasmCompileError("py2wasm artifact is missing the Cosmos host bridge")
		exports = tuple(name for name, _, _ in parsed_exports)
		export_kinds = {name: kind for name, kind, _ in parsed_exports}
		required_exports = {"memory", "_start", "cosmos_turn"}
		if set(exports) != required_exports:
			raise Py2WasmCompileError("py2wasm artifact must have only the Cosmos runtime exports")
		if export_kinds["memory"] != 2 or export_kinds["_start"] != 0 or export_kinds["cosmos_turn"] != 0:
			raise Py2WasmCompileError("py2wasm artifact exports have invalid kinds")
		if pages is None:
			raise Py2WasmCompileError("py2wasm artifact has no defined memory")
		if pages > MAX_INITIAL_MEMORY_PAGES:
			raise Py2WasmCompileError(
				f"py2wasm artifact starts with {pages} memory pages; limit is {MAX_INITIAL_MEMORY_PAGES}"
			)
		return Py2WasmArtifact(
			binary=binary,
			digest=hashlib.sha256(binary).hexdigest(),
			imports=imports,
			exports=exports,
			initial_memory_pages=pages,
		)

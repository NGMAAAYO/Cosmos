"""
Auto-build script for cosmos_core C++ extension.
Checks if the compiled module exists and is up-to-date, builds if needed.
Uses pybind11 directly with setuptools — no cmake required.
"""
import os
import sys
import subprocess
import hashlib
import sysconfig
import glob


def _get_core_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "core")


def _get_source_hash(core_dir):
    """Compute hash of the C++ source to detect changes."""
    src_file = os.path.join(core_dir, "src", "cosmos_core.cpp")
    h = hashlib.md5()
    if os.path.exists(src_file):
        with open(src_file, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def _find_module(core_dir):
    """Find the compiled module file (.pyd on Windows, .so on Linux/Mac)."""
    patterns = [
        os.path.join(core_dir, "cosmos_core*.pyd"),
        os.path.join(core_dir, "cosmos_core*.so"),
        os.path.join(core_dir, "cosmos_core*.dylib"),
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
    return None


def _get_hash_file(core_dir):
    return os.path.join(core_dir, ".build_hash")


def needs_build(core_dir=None):
    """Check if the C++ module needs (re)building."""
    if core_dir is None:
        core_dir = _get_core_dir()

    module_path = _find_module(core_dir)
    hash_file = _get_hash_file(core_dir)

    if module_path is None:
        return True

    current_hash = _get_source_hash(core_dir)
    if os.path.exists(hash_file):
        with open(hash_file, "r") as f:
            stored_hash = f.read().strip()
        if stored_hash == current_hash:
            return False

    return True


def build_core(core_dir=None, verbose=False):
    """Build the C++ core module using pybind11 and setuptools."""
    if core_dir is None:
        core_dir = _get_core_dir()

    setup_py = os.path.join(core_dir, "_setup.py")
    src_file = os.path.join(core_dir, "src", "cosmos_core.cpp")

    # Write a temporary setup.py for building
    setup_content = f'''
import os
import sys
from setuptools import setup, Extension
import pybind11

ext = Extension(
    "cosmos_core",
    sources=[{repr(src_file)}],
    include_dirs=[pybind11.get_include(), pybind11.get_include(user=True)],
    language="c++",
    extra_compile_args=["/std:c++17", "/O2", "/EHsc", "/utf-8"] if sys.platform == "win32"
        else ["-std=c++17", "-O3", "-fvisibility=hidden"],
)

setup(
    name="cosmos_core",
    ext_modules=[ext],
    script_args=["build_ext", "--inplace"],
)
'''
    with open(setup_py, "w") as f:
        f.write(setup_content)

    print("[cosmos] Building C++ core module...")

    try:
        result = subprocess.run(
            [sys.executable, setup_py],
            cwd=core_dir,
            capture_output=not verbose,
            text=True,
        )
        if result.returncode != 0:
            if not verbose and result.stderr:
                print(result.stderr[-500:])
            print("[cosmos] Build failed. Falling back to pure Python core.")
            return False
    except Exception as e:
        print(f"[cosmos] Build error: {e}")
        print("[cosmos] Falling back to pure Python core.")
        return False
    finally:
        # Clean up temporary setup.py
        if os.path.exists(setup_py):
            os.remove(setup_py)

    # Verify the module was built
    if _find_module(core_dir) is None:
        print("[cosmos] Module file not found after build. Falling back to pure Python core.")
        return False

    # Save hash
    current_hash = _get_source_hash(core_dir)
    with open(_get_hash_file(core_dir), "w") as f:
        f.write(current_hash)

    print("[cosmos] C++ core module built successfully.")
    return True


def ensure_core_built(verbose=False):
    """Ensure the C++ core module is built. Returns True if C++ module is available."""
    core_dir = _get_core_dir()
    if needs_build(core_dir):
        return build_core(core_dir, verbose)
    return True


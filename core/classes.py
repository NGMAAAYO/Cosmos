"""
Classes module shim - exports C++ types when available, falls back to pure Python.
"""
try:
    from core.cosmos_core import Map
except ImportError:
    from core._classes_py import Map

__all__ = ["Map"]
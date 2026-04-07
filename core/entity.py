"""
Entity module shim - exports C++ types when available, falls back to pure Python.
"""
try:
    from core.cosmos_core import Controller, Entity
except ImportError:
    from core._entity_py import Controller, Entity

__all__ = ["Controller", "Entity"]
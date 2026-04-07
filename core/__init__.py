"""
Core module - tries to use C++ accelerated version, falls back to pure Python.
"""
_USE_NATIVE = False

try:
    from core.cosmos_core import (
        Direction, MapLocation, EntityType, EntityInfo, Team, Map, Controller, Entity
    )
    _USE_NATIVE = True
except ImportError:
    pass

if not _USE_NATIVE:
    from core._api_py import Direction, MapLocation, EntityType, EntityInfo, Team
    from core._classes_py import Map
    from core._entity_py import Controller, Entity

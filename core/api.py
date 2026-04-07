"""
API module shim - exports C++ types when available, falls back to pure Python.
"""
try:
    from core.cosmos_core import Direction, MapLocation, EntityType, EntityInfo, Team
except ImportError:
    from core._api_py import Direction, MapLocation, EntityType, EntityInfo, Team

__all__ = ["Direction", "MapLocation", "EntityType", "EntityInfo", "Team"]

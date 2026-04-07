try:
    from core.cosmos_core import Direction, MapLocation, EntityType, EntityInfo, Team
except ImportError:
    from core._api_py import Direction, MapLocation, EntityType, EntityInfo, Team

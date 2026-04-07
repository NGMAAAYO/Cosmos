try:
    from core.cosmos_core import Controller, Entity
except ImportError:
    from core._entity_py import Controller, Entity

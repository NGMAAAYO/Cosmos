"""Capability-only Cosmos API facade executed inside the Wasm guest."""

from _cosmos import call as _raw_call, call_float as _raw_call_float

_ERROR = -(1 << 63)
_MASK32 = (1 << 32) - 1
_MASK64 = (1 << 64) - 1


def bit_length(value):
    """CPython-compatible ``int.bit_length`` used by the source lowering."""
    value = abs(int(value))
    result = 0
    while value:
        result += 1
        value >>= 1
    return result


def bit_count(value):
    """CPython-compatible ``int.bit_count`` used by the source lowering."""
    value = abs(int(value))
    result = 0
    while value:
        result += value & 1
        value >>= 1
    return result


def _call(op, a=0, b=0, c=0):
    value = _raw_call(op, a, b, c)
    if value == _ERROR:
        raise RuntimeError("game API call failed")
    return value


def _call_float(op, a=0, b=0, c=0):
    value = _raw_call_float(op, a, b, c)
    if value != value:
        raise RuntimeError("game API call failed")
    return value


def _signed32(value):
    value &= _MASK32
    return value - (1 << 32) if value >= (1 << 31) else value


def _pack_location(location):
    value = ((int(location.x) & _MASK32) << 32) | (int(location.y) & _MASK32)
    return value - (1 << 64) if value >= (1 << 63) else value


def _unpack_location(value):
    value &= _MASK64
    return MapLocation(_signed32(value >> 32), _signed32(value))


def _pack_direction(direction):
    dx, dy = int(direction.dx), int(direction.dy)
    if dx < -1 or dx > 1 or dy < -1 or dy > 1:
        raise ValueError("direction components must be between -1 and 1")
    return (dx + 1) * 3 + dy + 1


def _team_code(team):
    return -1 if team.tag == "Neutral" else int(team.tag)


class Direction:
    def __init__(self, dx=0, dy=0):
        self.dx = int(dx)
        self.dy = int(dy)

    def __repr__(self):
        names = (
            ("south_west", "west", "north_west"),
            ("south", "center", "north"),
            ("south_east", "east", "north_east"),
        )
        if -1 <= self.dx <= 1 and -1 <= self.dy <= 1:
            return names[self.dx + 1][self.dy + 1]
        return "direction(%d, %d)" % (self.dx, self.dy)

    __str__ = __repr__

    def __eq__(self, other):
        return isinstance(other, Direction) and self.dx == other.dx and self.dy == other.dy

    @staticmethod
    def center(): return Direction(0, 0)

    @staticmethod
    def north(): return Direction(0, 1)

    @staticmethod
    def north_east(): return Direction(1, 1)

    @staticmethod
    def east(): return Direction(1, 0)

    @staticmethod
    def south_east(): return Direction(1, -1)

    @staticmethod
    def south(): return Direction(0, -1)

    @staticmethod
    def south_west(): return Direction(-1, -1)

    @staticmethod
    def west(): return Direction(-1, 0)

    @staticmethod
    def north_west(): return Direction(-1, 1)

    @staticmethod
    def all_directions():
        return [Direction(dx, dy) for dx in (0, -1, 1) for dy in (0, -1, 1)]

    @staticmethod
    def cardinal_directions():
        return [Direction.north(), Direction.south(), Direction.east(), Direction.west()]

    def get_dx(self): return self.dx
    def get_dy(self): return self.dy
    def opposite(self): return Direction(-self.dx, -self.dy)

    def rotate_left(self):
        if self.dx == 0 and self.dy == 0:
            return Direction.center()
        ordered = (
            Direction.east(), Direction.north_east(), Direction.north(), Direction.north_west(),
            Direction.west(), Direction.south_west(), Direction.south(), Direction.south_east(),
        )
        for index, direction in enumerate(ordered):
            if self == direction:
                return ordered[(index + 1) % 8]
        return Direction.center()

    def rotate_right(self):
        if self.dx == 0 and self.dy == 0:
            return Direction.center()
        ordered = (
            Direction.east(), Direction.north_east(), Direction.north(), Direction.north_west(),
            Direction.west(), Direction.south_west(), Direction.south(), Direction.south_east(),
        )
        for index, direction in enumerate(ordered):
            if self == direction:
                return ordered[(index + 7) % 8]
        return Direction.center()

    def equals(self, other):
        return self == other


class MapLocation:
    def __init__(self, x=0, y=0):
        self.x = int(x)
        self.y = int(y)

    def __repr__(self):
        return "(%d, %d)" % (self.x, self.y)

    __str__ = __repr__

    def __eq__(self, other):
        return isinstance(other, MapLocation) and self.x == other.x and self.y == other.y

    def add(self, direction): return MapLocation(self.x + direction.dx, self.y + direction.dy)
    def subtract(self, direction): return MapLocation(self.x - direction.dx, self.y - direction.dy)
    def translate(self, dx, dy): return MapLocation(self.x + int(dx), self.y + int(dy))

    def direction_to(self, location):
        dx = 1 if location.x > self.x else (-1 if location.x < self.x else 0)
        dy = 1 if location.y > self.y else (-1 if location.y < self.y else 0)
        return Direction(dx, dy)

    def distance_to(self, location):
        dx, dy = location.x - self.x, location.y - self.y
        return dx * dx + dy * dy

    def is_adjacent_to(self, location):
        return abs(self.x - location.x) <= 1 and abs(self.y - location.y) <= 1

    def equals(self, other): return self == other
    def to_tuple(self): return (self.x, self.y)


class EntityType:
    _VALUES = {
        "planet": (2.0, 2, 1.0, 40, 0, 40, 0),
        "destroyer": (1.0, 9, 1.0, 25, 10, 25, 1),
        "miner": (2.0, 0, 1.0, 20, 0, 20, 2),
        "scout": (1.5, 12, 0.7, 40, 10, 30, 3),
    }

    def __init__(self, name):
        if name not in self._VALUES:
            raise RuntimeError("invalid entity type")
        self.name = name
        values = self._VALUES[name]
        self.action_cooldown = values[0]
        self.action_radius = values[1]
        self.defence_ratio = values[2]
        self.detection_radius = values[3]
        self.initial_cooldown = values[4]
        self.sensor_radius = values[5]
        self._code = values[6]

    def __repr__(self): return self.name
    __str__ = __repr__

    def __eq__(self, other):
        if isinstance(other, EntityType):
            return self.name == other.name
        if isinstance(other, str):
            return self.name == other
        return False

    @staticmethod
    def all_types():
        return [EntityType(name) for name in ("destroyer", "miner", "scout", "planet")]


class Team:
    def __init__(self, tag): self.tag = str(tag)
    def __repr__(self): return self.tag
    __str__ = __repr__

    def __eq__(self, other):
        if isinstance(other, Team):
            return self.tag == other.tag
        if isinstance(other, str):
            return self.tag == other
        return False

    def is_player(self): return self.tag != "Neutral"


class EntityInfo:
    def __init__(self, defence, rid, energy, location, team, entity_type, radio):
        self.energy = int(energy)
        self.defence = int(energy) if entity_type.name == "planet" else int(defence)
        self.init_defence = int(defence)
        self.ID = int(rid)
        self.location = location
        self.team = team
        self.type = entity_type
        self.radio = int(radio)

    def copy(self):
        result = EntityInfo(
            self.defence, self.ID, self.energy,
            MapLocation(self.location.x, self.location.y),
            Team(self.team.tag), EntityType(self.type.name), self.radio,
        )
        result.init_defence = self.init_defence
        return result

    def to_dict(self):
        return {
            "ID": self.ID,
            "energy": self.energy,
            "defence": self.defence,
            "location": self.location.to_tuple(),
            "team": self.team.tag,
            "type": self.type.name,
            "radio": self.radio,
        }


class Controller:
    def __init__(self):
        self._nearby = None

    def _begin_turn(self):
        self._nearby = None

    def get_round_num(self): return _call(1)
    def get_cooldown_turns(self): return _call(2)
    def get_energy(self): return _call(3)
    def get_defence(self): return _call(4)
    def get_id(self): return _call(5)
    def get_location(self): return _unpack_location(_call(6))
    def get_team(self):
        value = _call(7)
        return Team("Neutral" if value == -1 else str(value))
    def get_type(self): return EntityType(("planet", "destroyer", "miner", "scout")[_call(8)])
    def get_radio(self): return _call(9)
    def get_charge_point(self): return _call(10)
    def get_entity_count(self): return _call(11)
    def is_ready(self): return bool(_call(12))

    def get_all_teams(self):
        result = []
        for index in range(_call(13)):
            value = _call(14, index)
            result.append(Team("Neutral" if value == -1 else str(value)))
        return result

    def get_opponent(self):
        result = []
        for index in range(_call(15)):
            value = _call(16, index)
            result.append(Team("Neutral" if value == -1 else str(value)))
        return result

    def get_overdrive_factor(self, team, round=0):
        return _call_float(17, _team_code(team), int(round))

    def adjacent_location(self, direction): return self.get_location().add(direction)
    def is_opponent(self, team): return self.get_team() != team
    def is_blocked(self, direction): return bool(_call(19, _pack_direction(direction)))
    def is_location_occupied(self, location): return bool(_call(20, _pack_location(location)))
    def on_the_map(self, location): return bool(_call(21, _pack_location(location)))
    def can_detect_location(self, location): return bool(_call(22, _pack_location(location)))
    def can_detect_radius(self, radius): return bool(_call(23, int(radius)))
    def can_sense_location(self, location): return bool(_call(24, _pack_location(location)))
    def can_sense_radius(self, radius): return bool(_call(25, int(radius)))
    def sense_aether(self, location): return _call_float(26, _pack_location(location))

    def _all_nearby(self):
        if self._nearby is None:
            entities = []
            for index in range(_call(41)):
                team = _call(47, index)
                entities.append(EntityInfo(
                    _call(45, index), _call(42, index), _call(43, index),
                    _unpack_location(_call(46, index)),
                    Team("Neutral" if team == -1 else str(team)),
                    EntityType(("planet", "destroyer", "miner", "scout")[_call(48, index)]),
                    _call(49, index),
                ))
                entities[-1].defence = _call(44, index)
            self._nearby = entities
        return self._nearby

    def sense_entity(self, target):
        if isinstance(target, int):
            for entity in self._all_nearby():
                if entity.ID == target:
                    return entity
        elif isinstance(target, MapLocation):
            for entity in self._all_nearby():
                if entity.location == target:
                    return entity
        return None

    def sense_nearby_entities(self, center=None, radius=None, teams=None):
        center = self.get_location() if center is None else center
        radius = self.get_type().sensor_radius if radius is None else int(radius)
        result = []
        for entity in self._all_nearby():
            if entity.location.distance_to(center) > radius:
                continue
            if teams is not None and not any(entity.team == team for team in teams):
                continue
            result.append(entity)
        return result

    def detect_nearby_entities(self, radius):
        return [_unpack_location(_call(51, index)) for index in range(_call(50, int(radius)))]

    def can_charge(self, energy): return bool(_call(27, int(energy)))

    def can_build(self, entity_type, direction, energy):
        return bool(_call(28, entity_type._code, _pack_direction(direction), int(energy)))

    def can_overdrive(self, radius): return bool(_call(29, int(radius)))

    def can_analyze(self, target):
        if isinstance(target, int): return bool(_call(30, target))
        if isinstance(target, MapLocation): return bool(_call(31, _pack_location(target)))
        return False

    def can_move(self, direction): return bool(_call(32, _pack_direction(direction)))

    @staticmethod
    def can_set_radio(radio):
        return bool(_call(33, int(radio)))

    def charge(self, energy): _call(34, int(energy))

    def build(self, entity_type, direction, energy):
        _call(35, entity_type._code, _pack_direction(direction), int(energy))

    def overdrive(self, radius): _call(36, int(radius))

    def analyze(self, target):
        if isinstance(target, int): _call(37, target)
        elif isinstance(target, MapLocation): _call(38, _pack_location(target))
        else: raise RuntimeError("cannot analyze this target")

    def move(self, direction): _call(39, _pack_direction(direction))
    def set_radio(self, radio): _call(40, int(radio))
    def random_int(self, limit): return _call(52, int(limit))


__all__ = ["Direction", "MapLocation", "EntityType", "EntityInfo", "Team"]

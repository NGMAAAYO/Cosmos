"""Generate the six deterministic competitive maps shipped with Cosmos.

The terrain uses mirrored harmonic noise and explicit geometric bands.  It does
not import or call the legacy random map generator.  Aether value 0.0001 is
reserved for deliberate black-hole barriers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path


WALL_AETHER = 0.0001
MAP_ROOT = Path(__file__).resolve().parents[1] / "maps"


DESIGNED_MAPS = {
    "fang": {
        "category": "duel",
        "size": (33, 33),
        "initial_planets": 1,
        "neutral_planets": 0,
        "team_build_rate": 0.32,
    },
    "bastion": {
        "category": "duel",
        "size": (72, 48),
        "initial_planets": 2,
        "neutral_planets": 0,
        "team_build_rate": 0.32,
    },
    "crown": {
        "category": "center",
        "size": (41, 41),
        "initial_planets": 1,
        "neutral_planets": 1,
        "team_build_rate": 0.28,
    },
    "crucible": {
        "category": "center",
        "size": (81, 61),
        "initial_planets": 2,
        "neutral_planets": 1,
        "team_build_rate": 0.28,
    },
    "fork": {
        "category": "lanes",
        "size": (49, 37),
        "initial_planets": 1,
        "neutral_planets": 2,
        "team_build_rate": 0.30,
    },
    "delta": {
        "category": "lanes",
        "size": (97, 65),
        "initial_planets": 2,
        "neutral_planets": 2,
        "team_build_rate": 0.30,
    },
}


def _clamp(value: float, lower: float = 0.2, upper: float = 0.95) -> float:
    return max(lower, min(upper, value))


def _noise(x: int, y: int, width: int, height: int, phase: int) -> float:
    """Small deterministic noise mirrored across both map axes."""
    u = min(x, width - 1 - x)
    v = min(y, height - 1 - y)
    first = math.sin((u + phase) * math.pi / 7.0) * math.cos((v + phase) * math.pi / 9.0)
    second = math.cos((2 * u + v + phase) * math.pi / 13.0)
    third = math.sin((u + 3 * v + phase) * math.pi / 17.0)
    return 0.55 * first + 0.30 * second + 0.15 * third


def _planet(x: int, y: int, team: str, energy: int = 150) -> dict:
    return {"x": x, "y": y, "team": team, "energy": energy}


def _build_map(
    width: int,
    height: int,
    terrain,
    planets: list[dict],
    planet_aether: dict[tuple[int, int], float],
) -> dict:
    cells = []
    for x in range(width):
        for y in range(height):
            value = terrain(x, y)
            if (x, y) in planet_aether:
                value = planet_aether[(x, y)]
            elif value != WALL_AETHER:
                value = _clamp(value)
            cells.append({"x": x, "y": y, "aether": round(value, 6)})
    return {
        "players": 2,
        "map_size": [width, height],
        "map": cells,
        "planets": planets,
    }


def _fang() -> dict:
    width = height = 33
    center = 16

    def terrain(x: int, y: int) -> float:
        dx, dy = abs(x - center), abs(y - center)
        value = 0.43 + 0.018 * _noise(x, y, width, height, 1)
        if dy <= 2:
            value = 0.78
        elif dy <= 5:
            value = max(value, 0.60)
        if abs(dx - 2 * dy) <= 2:
            value = max(value, 0.66)
        return value

    planets = [_planet(4, 16, "0"), _planet(28, 16, "1")]
    return _build_map(width, height, terrain, planets, {(4, 16): 0.64, (28, 16): 0.64})


def _bastion() -> dict:
    width, height = 72, 48

    def terrain(x: int, y: int) -> float:
        wall_column = x in {25, 26, 45, 46}
        wall_segment = 6 <= y <= 17 or 30 <= y <= 41
        if wall_column and wall_segment:
            return WALL_AETHER

        value = 0.40 + 0.018 * _noise(x, y, width, height, 2)
        if 27 <= x <= 44:
            value = max(value, 0.56)
        if y <= 5 or y >= 42:
            value = max(value, 0.68)
        if 20 <= y <= 27:
            value = max(value, 0.72)
        if y in range(17, 21) or y in range(27, 31):
            value = max(value, 0.58)
        return value

    planets = [
        _planet(7, 14, "0"),
        _planet(7, 33, "0"),
        _planet(64, 14, "1"),
        _planet(64, 33, "1"),
    ]
    aether = {(p["x"], p["y"]): 0.32 for p in planets}
    return _build_map(width, height, terrain, planets, aether)


def _crown() -> dict:
    width = height = 41
    center = 20

    def terrain(x: int, y: int) -> float:
        dx, dy = abs(x - center), abs(y - center)
        ring = max(dx, dy)
        if 6 <= ring <= 7 and dx > 1 and dy > 1:
            return WALL_AETHER

        value = 0.42 + 0.018 * _noise(x, y, width, height, 3)
        if ring <= 5:
            value = 0.84
        elif dx <= 2 or dy <= 2:
            value = max(value, 0.70)
        elif ring <= 11:
            value = max(value, 0.52)
        return value

    planets = [
        _planet(4, 20, "0"),
        _planet(36, 20, "1"),
        _planet(20, 20, "Neutral", 75),
    ]
    aether = {(4, 20): 0.56, (36, 20): 0.56, (20, 20): 0.72}
    return _build_map(width, height, terrain, planets, aether)


def _crucible() -> dict:
    width, height = 81, 61
    center_x, center_y = 40, 30

    def terrain(x: int, y: int) -> float:
        dx, dy = abs(x - center_x), abs(y - center_y)
        ring = max(dx, dy)
        if 10 <= ring <= 11 and dx > 2 and dy > 2:
            return WALL_AETHER

        value = 0.36 + 0.02 * _noise(x, y, width, height, 4)
        if ring <= 9:
            value = 0.82
        elif dx <= 3 or dy <= 3:
            value = max(value, 0.64)
        if abs(dx - dy) <= 2:
            value = max(value, 0.70)
        return value

    planets = [
        _planet(8, 18, "0"),
        _planet(8, 42, "0"),
        _planet(72, 18, "1"),
        _planet(72, 42, "1"),
        _planet(40, 30, "Neutral", 75),
    ]
    aether = {(p["x"], p["y"]): 0.28 for p in planets if p["team"] != "Neutral"}
    aether[(40, 30)] = 0.72
    return _build_map(width, height, terrain, planets, aether)


def _fork() -> dict:
    width, height = 49, 37
    center_x, center_y = 24, 18

    def terrain(x: int, y: int) -> float:
        in_barrier = 12 <= x <= 36 and abs(y - center_y) <= 1
        in_gate = min(abs(x - gate_x) for gate_x in (16, 24, 32)) <= 1
        if in_barrier and not in_gate:
            return WALL_AETHER

        upper_line = 8 + 0.5 * abs(x - center_x)
        lower_line = height - 1 - upper_line
        lane_distance = min(abs(y - upper_line), abs(y - lower_line))
        value = 0.38 + 0.018 * _noise(x, y, width, height, 5)
        if lane_distance <= 2:
            value = 0.78
        elif lane_distance <= 4:
            value = max(value, 0.58)
        if abs(y - center_y) <= 2:
            value = max(value, 0.46)
        return value

    planets = [
        _planet(4, 18, "0"),
        _planet(44, 18, "1"),
        _planet(24, 8, "Neutral", 100),
        _planet(24, 28, "Neutral", 100),
    ]
    aether = {
        (4, 18): 0.60,
        (44, 18): 0.60,
        (24, 8): 0.48,
        (24, 28): 0.48,
    }
    return _build_map(width, height, terrain, planets, aether)


def _delta() -> dict:
    width, height = 97, 65
    center_x, center_y = 48, 32

    def terrain(x: int, y: int) -> float:
        wall_band = (25 <= y <= 28 or 36 <= y <= 39) and 18 <= x <= 78
        in_gate = min(abs(x - gate_x) for gate_x in (32, 48, 64)) <= 1
        if wall_band and not in_gate:
            return WALL_AETHER

        upper_line = 14 + abs(x - center_x) / 20.0
        lower_line = height - 1 - upper_line
        lane_distance = min(abs(y - upper_line), abs(y - lower_line))
        value = 0.32 + 0.02 * _noise(x, y, width, height, 6)
        if lane_distance <= 3:
            value = 0.80
        elif lane_distance <= 6:
            value = max(value, 0.54)
        if abs(y - center_y) <= 2:
            value = max(value, 0.62)
        return value

    planets = [
        _planet(8, 16, "0"),
        _planet(8, 48, "0"),
        _planet(88, 16, "1"),
        _planet(88, 48, "1"),
        _planet(48, 14, "Neutral", 100),
        _planet(48, 50, "Neutral", 100),
    ]
    aether = {(p["x"], p["y"]): 0.30 for p in planets if p["team"] != "Neutral"}
    aether[(48, 14)] = 0.48
    aether[(48, 50)] = 0.48
    return _build_map(width, height, terrain, planets, aether)


BUILDERS = {
    "fang": _fang,
    "bastion": _bastion,
    "crown": _crown,
    "crucible": _crucible,
    "fork": _fork,
    "delta": _delta,
}


def write_maps(output_root: Path = MAP_ROOT) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for name, builder in BUILDERS.items():
        path = output_root / f"{name}.json"
        path.write_text(
            json.dumps(builder(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    write_maps()

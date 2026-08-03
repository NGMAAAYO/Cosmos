import json
import random
import sys
import tempfile
import unittest
from collections import Counter, deque
from pathlib import Path

from core.game import Instance
from utils.designed_maps import DESIGNED_MAPS, WALL_AETHER, write_maps


MAP_ROOT = Path(__file__).resolve().parents[1] / "maps"


class DesignedMapTestCase(unittest.TestCase):
    @staticmethod
    def load_map(name):
        return json.loads((MAP_ROOT / f"{name}.json").read_text(encoding="utf-8"))

    @staticmethod
    def aether_grid(data):
        return {(cell["x"], cell["y"]): cell["aether"] for cell in data["map"]}

    @staticmethod
    def reachable(grid, size, origin):
        width, height = size
        visited = {origin}
        queue = deque([origin])
        while queue:
            x, y = queue.popleft()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nxt = (x + dx, y + dy)
                    if not (0 <= nxt[0] < width and 0 <= nxt[1] < height):
                        continue
                    if nxt in visited or grid[nxt] <= WALL_AETHER:
                        continue
                    visited.add(nxt)
                    queue.append(nxt)
        return visited

    @staticmethod
    def articulation_points(grid, size):
        """Return open cells whose removal disconnects the 8-neighbour graph."""
        width, height = size
        open_cells = {point for point, value in grid.items() if value > WALL_AETHER}
        sys.setrecursionlimit(max(sys.getrecursionlimit(), width * height + 100))
        discovered = {}
        low = {}
        parent = {}
        articulation = set()
        clock = 0

        def visit(point):
            nonlocal clock
            clock += 1
            discovered[point] = low[point] = clock
            children = 0
            x, y = point
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbour = (x + dx, y + dy)
                    if neighbour not in open_cells:
                        continue
                    if neighbour not in discovered:
                        parent[neighbour] = point
                        children += 1
                        visit(neighbour)
                        low[point] = min(low[point], low[neighbour])
                        if point not in parent and children > 1:
                            articulation.add(point)
                        if point in parent and low[neighbour] >= discovered[point]:
                            articulation.add(point)
                    elif parent.get(point) != neighbour:
                        low[point] = min(low[point], discovered[neighbour])

        visit(next(iter(open_cells)))
        return articulation

    def test_designed_maps_have_expected_structure_and_symmetry(self):
        self.assertEqual(Counter(spec["category"] for spec in DESIGNED_MAPS.values()), {
            "duel": 2,
            "center": 2,
            "lanes": 2,
        })

        for name, spec in DESIGNED_MAPS.items():
            with self.subTest(map=name):
                data = self.load_map(name)
                width, height = data["map_size"]
                self.assertEqual((width, height), spec["size"])
                self.assertEqual(data["players"], 2)

                grid = self.aether_grid(data)
                self.assertEqual(len(grid), width * height)
                for x in range(width):
                    for y in range(height):
                        value = grid[(x, y)]
                        self.assertEqual(value, grid[(width - 1 - x, y)])
                        self.assertEqual(value, grid[(x, height - 1 - y)])
                        self.assertTrue(value == WALL_AETHER or 0.2 <= value <= 0.95)

                planets = data["planets"]
                self.assertEqual(len({(p["x"], p["y"]) for p in planets}), len(planets))
                counts = Counter(p["team"] for p in planets)
                self.assertEqual(counts["0"], spec["initial_planets"])
                self.assertEqual(counts["1"], spec["initial_planets"])
                self.assertEqual(counts["Neutral"], spec["neutral_planets"])

                team_zero = sorted((p["x"], p["y"], p["energy"]) for p in planets if p["team"] == "0")
                team_one = sorted((width - 1 - p["x"], p["y"], p["energy"]) for p in planets if p["team"] == "1")
                self.assertEqual(team_zero, team_one)

                start_rate = sum(grid[(p["x"], p["y"])] / 2 for p in planets if p["team"] == "0")
                self.assertAlmostEqual(start_rate, spec["team_build_rate"])

                origin = (team_zero[0][0], team_zero[0][1])
                reachable = self.reachable(grid, (width, height), origin)
                for planet in planets:
                    self.assertIn((planet["x"], planet["y"]), reachable)
                self.assertEqual(self.articulation_points(grid, (width, height)), set())

    def test_map_directory_contains_only_supported_maps(self):
        expected = {f"{name}.json" for name in DESIGNED_MAPS}
        expected.add("maptestsmall.json")
        actual = {path.name for path in MAP_ROOT.glob("*.json")}
        self.assertEqual(actual, expected)

    def test_map_objective_layouts_match_their_categories(self):
        for name in ("fang", "bastion"):
            self.assertFalse(any(p["team"] == "Neutral" for p in self.load_map(name)["planets"]))

        for name in ("crown", "crucible"):
            data = self.load_map(name)
            neutral = [p for p in data["planets"] if p["team"] == "Neutral"]
            self.assertEqual(len(neutral), 1)
            self.assertEqual(neutral[0]["x"], data["map_size"][0] // 2)
            self.assertEqual(neutral[0]["energy"], 75)

        for name in ("fork", "delta"):
            data = self.load_map(name)
            width, height = data["map_size"]
            neutral = sorted(
                (p["x"], p["y"], p["energy"])
                for p in data["planets"]
                if p["team"] == "Neutral"
            )
            self.assertEqual(len(neutral), 2)
            self.assertEqual(neutral[0][0], width // 2)
            self.assertEqual(neutral[1][0], width // 2)
            self.assertEqual(neutral[0][1] + neutral[1][1], height - 1)
            self.assertEqual(neutral[0][2], 100)
            self.assertEqual(neutral[1][2], 100)

    def test_committed_maps_match_the_deterministic_generator(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            generated_root = Path(temp_dir)
            write_maps(generated_root)
            for name in DESIGNED_MAPS:
                with self.subTest(map=name):
                    expected = (MAP_ROOT / f"{name}.json").read_text(encoding="utf-8")
                    generated = (generated_root / f"{name}.json").read_text(encoding="utf-8")
                    self.assertEqual(generated, expected)

    def test_designed_maps_load_and_run_in_the_engine(self):
        for name in DESIGNED_MAPS:
            with self.subTest(map=name):
                random.seed(20260803)
                game = Instance(
                    ["noact", "noact"],
                    str(MAP_ROOT / f"{name}.json"),
                    1,
                    debug=True,
                    show_progress=False,
                )
                try:
                    game.next_round()
                    self.assertEqual(game.round, 1)
                finally:
                    game.close()


if __name__ == "__main__":
    unittest.main()

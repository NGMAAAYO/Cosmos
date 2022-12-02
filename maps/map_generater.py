import random
import json


def randomize_aether(x, y):
	result = []
	for i in range(x):
		for j in range(y // 2):
			aether = random.uniform(0.2, 1.0)
			result.append({"x": i, "y": j, "aether": aether})
			result.append({"x": i, "y": y - j - 1, "aether": aether})
	return result


def gen_planet(x, y, team, res=150):
	if team == "Neutral":
		return {"x": x, "y": y, "team": "Neutral", "energy": res}
	else:
		return {"x": x, "y": y, "team": str(team), "energy": 150}


if __name__ == '__main__':
	planets = [gen_planet(14, 16, 0), gen_planet(28, 16, 0), gen_planet(34, 16, 1), gen_planet(50, 16, 1)]
	tmap = randomize_aether(64, 32)

	f = open("maptestbigrect.json", "w", encoding="utf-8")
	f.write(json.dumps({"players": 2, "map_size": (64, 32), "map": tmap, "planets": planets}))
	f.close()

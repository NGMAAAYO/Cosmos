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
	planets = [gen_planet(6, 6, 0), gen_planet(28, 28, 1)]
	tmap = randomize_aether(32, 32)

	f = open("maptestsmall.json", "w", encoding="utf-8")
	f.write(json.dumps({"players": 2, "map_size": (32, 32), "map": tmap, "planets": planets}))
	f.close()

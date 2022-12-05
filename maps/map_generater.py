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
	map_name = "multi_square_x64_4"
	x = 64
	y = 64
	planets = [gen_planet(32, 32, "Neutral"), gen_planet(16, 16, 0), gen_planet(48, 48, 1), gen_planet(16, 48, 2), gen_planet(48, 16, 3)]
	tmap = randomize_aether(x, y)

	f = open("{}.json".format(map_name), "w", encoding="utf-8")
	f.write(json.dumps({"players": 4, "map_size": (x, y), "map": tmap, "planets": planets}))
	f.close()

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
	map_name = "multi_square_x100_4"
	x = 100
	y = 100
	planets = [gen_planet(0, 0, "Neutral"), gen_planet(99, 99, "Neutral"), gen_planet(99, 0, "Neutral"), gen_planet(0, 99, "Neutral"), gen_planet(35, 35, 0), gen_planet(63, 63, 1), gen_planet(35, 63, 2), gen_planet(63, 35, 3)]
	tmap = randomize_aether(x, y)

	f = open("./maps/{}.json".format(map_name), "w", encoding="utf-8")
	f.write(json.dumps({"players": 4, "map_size": (x, y), "map": tmap, "planets": planets}))
	f.close()

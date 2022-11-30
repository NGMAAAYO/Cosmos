
import random
import json

def randomize_aether(x, y):
	result = []
	for i in range(x):
		temp = []
		for j in range(y // 2):
			temp.append(random.uniform(0.2, 1.0))
		for j in temp[::-1]:
			temp.append(j)
		result.append(temp)
	return result

def add_planet(x, y, team, res=150):
	if team == "Neutral":
		planets.append({"x":x, "y":y, "team":"Neutral", "energy":res})
	else:
		planets.append({"x":x, "y":y, "team":str(team), "energy":150})



if __name__ == '__main__':
	tmap = []
	planets = []
	tmap = randomize_aether(32, 32)
	add_planet(6, 6, 1)
	add_planet(28, 28, 2)
	f = open("maptestsmall.json", "w", encoding="utf-8")
	f.write(json.dumps({"map":tmap, "planets":planets}))
	f.close()


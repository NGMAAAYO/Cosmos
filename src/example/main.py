import random

from src import template
from core.api import *


class Player(template.Player):
	def __init__(self):
		super().__init__()

	def random_move(self):
		d = random.choice(Direction.all_directions())
		if self.controller.can_move(d):
			self.controller.move(d)

	def run_planet(self):
		if self.controller.can_charge(1):
			self.controller.charge(1)

		t = random.choice([EntityType("destroyer"), EntityType("miner"), EntityType("scout")])
		d = random.choice(Direction.all_directions())
		e = self.controller.get_energy()
		if self.controller.can_build(t, d, e):
			self.controller.build(t, d, e)

	def run_destroyer(self):
		entities = self.controller.sense_nearby_entities()
		for entity in entities:
			if entity.team.tag != self.controller.get_team().tag:
				if self.controller.can_overdrive(self.controller.get_type().action_radius):
					self.controller.overdrive(self.controller.get_type().action_radius)
					return
		self.random_move()

	def run_miner(self):
		self.random_move()

	def run_scout(self):
		entities = self.controller.sense_nearby_entities()
		for entity in entities:
			if entity.team.tag != self.controller.get_team().tag and entity.type.name == "miner":
				if self.controller.can_analyze(entity.ID):
					self.controller.analyze(entity.ID)
					return
		self.random_move()

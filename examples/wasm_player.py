from core.api import *


class Player:
	def __init__(self):
		self.turns = 0

	def run(self, controller):
		self.turns += 1
		if controller.get_type() == EntityType("planet"):
			if controller.can_charge(1):
				controller.charge(1)
			return

		if not controller.is_ready():
			return

		for entity in controller.sense_nearby_entities(teams=controller.get_opponent()):
			direction = controller.get_location().direction_to(entity.location)
			if controller.can_move(direction):
				controller.move(direction)
				return

		for direction in Direction.all_directions():
			if controller.can_move(direction):
				controller.move(direction)
				return

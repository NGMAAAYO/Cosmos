class Player:
    def __init__(self):
        self.controller = None
    
    def run(self, controller):
        self.controller = controller
        entity_type = controller.get_type().type
        if entity_type == "planet":
            self.run_planet()
        elif entity_type == "destroyer":
            self.run_destroyer()
        elif entity_type == "miner":
            self.run_miner()
        elif entity_type == "scout":
            self.run_scout()
        return controller

    def run_planet(self):
        pass

    def run_destroyer(self):
        pass

    def run_miner(self):
        pass

    def run_scout(self):
        pass

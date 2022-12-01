from core.game import Instance

if __name__ == '__main__':
    game_instance = Instance(["example", "example"], "./maps/maptestsmall.json", 1000)
    game_instance.run()

import sc2, sys
from __init__ import run_ladder_game
from sc2 import Race, Difficulty
from sc2.player import Bot, Computer, Human
import random

# Load bot
from Overmind import Overmind
bot = Bot(Race.Zerg, Overmind())

# Start game
if __name__ == '__main__':
    if "--LadderServer" in sys.argv:
        # Ladder game started by LadderManager
        print("Starting ladder game...")
        run_ladder_game(bot)
    else:
        # Local game
        print("Starting local game...")
        map_name = random.choice(["CatalystLE"])
        #map_name = random.choice(["ProximaStationLE", "NewkirkPrecinctTE", "OdysseyLE", "MechDepotLE", "AscensiontoAiurLE", "BelShirVestigeLE"])
        #map_name = "(2)16-BitLE"
        sc2.run_game(sc2.maps.get(map_name), [
            #Human(Race.Terran),
            bot,
            Computer(Race.Random, Difficulty.VeryHard) # CheatInsane VeryHard
        ], realtime=False, save_replay_as="Example.SC2Replay")

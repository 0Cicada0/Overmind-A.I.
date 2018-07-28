from sc2.unit import Unit
from sc2.units import Units
from sc2.data import race_gas, race_worker, race_townhalls, ActionResult, Attribute, Race

import sc2 # pip install sc2
from sc2 import Race, Difficulty, run_game, maps
from sc2.constants import * # for autocomplete
from sc2.ids.unit_typeid import *
from sc2.ids.ability_id import *
from sc2.position import Point2, Point3
from sc2.helpers import ControlGroup

from sc2.player import Bot, Computer, Human
import math
import random
#from cannon_lover_bot import CannonLoverBot

class Overmind(sc2.BotAI):
    def __init__(self):
        self.ITERATIONS_PER_MINUTE = 2970
        self.max_workers = 80
        self.mboost_started = False
        self.maug_started = False
        self.grecon_started = False
        self.gspines_started = False
        self.order_queue = []
        self.expand_every = 1.25 * 60 # Second
        self.burrow_started = False
        self.creepTargetDistance = 15 # was 10
        self.creepTargetCountsAsReachedDistance = 10 # was 25
        self.creepSpreadInterval = 10
        self.stopMakingNewTumorsWhenAtCoverage = 0.8 # stops queens from putting down new tumors and save up transfuse energy
        self.defendRangeToTownhalls = 40
        self.hive_tech = False
        self.defending = False
        self.stop_worker = False
        self.stop_army = False
        self.strategy = "Unsure"
        self.stop_roaches = False
        self.stop_hydra = False
        self.attacking = False
        self.ovy_scout = False
        self.units_to_ignore = [DRONE, SCV, PROBE, EGG, LARVA, OVERLORD, OVERSEER, OBSERVER, BROODLING, INTERCEPTOR, MEDIVAC, CREEPTUMOR, CREEPTUMORBURROWED, CREEPTUMORQUEEN, CREEPTUMORMISSILE]
        self.Terran = [BARRACKS, COMMANDCENTER, ORBITALCOMMAND, MARINE, SCV, SUPPLYDEPOT, MARAUDER, REACTOR, TECHLAB]
        self.Zerg = [HATCHERY, LAIR, HIVE, SPAWNINGPOOL, DRONE, ZERGLING, QUEEN, OVERLORD]
        self.Protoss = [NEXUS, PYLON, GATEWAY, CYBERNETICSCORE, STALKER, ZEALOT, PHOTONCANNON, PROBE]
        self.remembered_enemy_units = []
        self.remembered_enemy_units_by_tag = {}
        self.remembered_friendly_units_by_tag = {}
        self.enemy_race = None
        self.queensAssignedHatcheries = {} # contains a list of queen: hatchery assignments (for injects)
        self.injectInterval = 100
        self.defending_queens = False
        self.stop_expand = False
        self.attack_supply = 193
        self.cannon_rush = False
        self.move = False
        self.emergency = False
        self.late_game = False
        self.not_attack_units = [PROBE, SCV, DRONE, OVERLORD, QUEEN, LARVA, EGG]
        self.enemy_supply = 200
        self.panic = False
        self.voidray = False
        self.expanding = False
        self.ov1_scout = False
        self.ov2_scout = False
        self.ov3_scout = False

    async def on_step(self, iteration):
        self.iteration = iteration
        hqa = self.townhalls.amount
        self.injectQueenLimit = hqa
        if iteration == 0:
            await self.chat_send("(glhf)")
        if self.get_game_time() > 850:
            self.late_game = True
        self.remember_enemy_units()
        self.remember_friendly_units()

        await self.distribute_workers()
        await self.ov_scout()
        await self.build_overlords()
        await self.expand()
        await self.build_workers()
        await self.find_race()
        await self.find_strategy()
        await self.doCreepSpread()
        await self.build_spawning_pool()    #Builds spawning pool for zerglings
        await self.upgrade_hatch()  #Upgrades hatch into lair
        await self.upgrade_lair()
        await self.build_evochamber()
        await self.build_queens()
        self.assignQueen(self.injectQueenLimit)
        await self.doQueenInjects(iteration)
        await self.set_rally_hatchery()
        await self.set_rally_lair()
        await self.set_rally_hive()
        await self.attack_rally_location()
        await self.defend_queens()
        await self.defend()
        await self.metabolic_boost()
        await self.attack()
        await self.check_cannon()
        await self.check_emergency()
        await self.check_enemy_supply()
        await self.build_infestation()
        #await self.pull_the_bios()
        await self.check_voidray()
        if self.get_game_time() > 60:
            await self.scout()
        #print(self.stop_worker)
        #print(self.stop_army)
        #print(self.strategy)

        #await self.queen_micro()
        
        if self.strategy == "hydra/ling/bane":
            await self.build_extractor()
            await self.upgrade_hydra_speed()
            await self.upgrade_hydra_range()
            await self.build_hydra()
            await self.hydra_den()
            await self.build_hydra_ling()
            await self.build_banenest()
            await self.build_banes()
            await self.upgrade()
            await self.rolly_polly()

        elif self.strategy == "muta/ling/bane":
            await self.build_extractor()
            await self.build_banenest()
            await self.build_banes()
            await self.rolly_polly()
            await self.upgrade()
            await self.spire()
            await self.build_muta_ling()
            await self.upgrade_flyer()


        elif self.strategy == "roach/hydra":
            await self.build_extractor()
            await self.roach_warren()
            await self.roach_micro()
            await self.research_burrow()
            await self.upgrade()
            await self.upgrade_roach()
            await self.upgrade_hydra_speed()
            await self.upgrade_hydra_range()
            await self.hydra_den()
            await self.build_roach_hydra()

        elif self.strategy == "hydra":
            await self.build_extractor()
            await self.upgrade()
            await self.upgrade_hydra_speed()
            await self.upgrade_hydra_range()
            await self.hydra_den()
            await self.build_hydra()

        await self.execute_order_queue()
    #async def late_game(self):
    async def check_voidray(self):
        enemy_units = self.remembered_enemy_units
        if enemy_units(VOIDRAY).amount > 2 and enemy_units(VOIDRAY).amount > enemy_units(STALKER).amount:
            self.strategy = "hydra"
        
    async def pull_the_bios(self):
        hatch =  self.townhalls.ready
        nearby_enemies = self.known_enemy_units.not_structure.filter(lambda unit: unit.type_id not in self.units_to_ignore).closer_than(30, hatch)
        if nearby_enemies.amount >= 1 and nearby_enemies.amount <= 15 and self.workers.exists:
            workers = self.workers.prefer_close_to(nearby_enemies.first).take(nearby_enemies.amount*2, False)

            for worker in workers:
                await self.do(worker.attack(nearby_enemies.closer_than(20, worker).closest_to(worker).position))    

    async def build_infestation(self):
        hq = self.townhalls.random
        if self.units(LAIR).exists:
            if self.can_afford(INFESTATIONPIT) and not self.already_pending(INFESTATIONPIT) and not self.units(INFESTATIONPIT).exists:
                if self.late_game:
                    await self.build(INFESTATIONPIT, near=hq.position.towards(self.game_info.map_center, 8))

    async def check_enemy_supply(self):
        army_units = self.units(ROACH).ready | self.units(HYDRALISK).ready | self.units(OVERSEER).ready | self.units(MUTALISK).ready | self.units(ZERGLING).ready | self.units(BANELING).ready
        self.enemy_supply = 0
        EnemyUnits = self.remembered_enemy_units.not_structure.filter(lambda x:x.type_id not in self.not_attack_units)
        #print(enemyUnitData)
        #print(vars(enemyUnitData))
        self.enemy_supply = sum([unit._type_data._proto.food_required for unit in EnemyUnits])
        self.my_supply = sum([unit._type_data._proto.food_required for unit in army_units])
        if self.enemy_supply > (self.my_supply * 1.4) and not self.expanding and not self.emergency and not self.get_game_time() > 180:
            self.panic = True
            self.stop_worker = True
            #print("Panic")
        elif self.enemy_supply <= self.my_supply and self.panic:
            self.panic = False
            self.stop_worker = False


    async def check_emergency(self):
        army_count = self.units(ROACH).amount | self.units(HYDRALISK).amount | self.units(OVERSEER).amount | self.units(MUTALISK).amount | self.units(ZERGLING).amount | self.units(BANELING).amount
        enemiesCloseToTh = None
        for th in self.townhalls:
            enemiesCloseToTh = self.known_enemy_units.closer_than(self.defendRangeToTownhalls, th.position)
        if not enemiesCloseToTh and self.emergency:
            self.stop_worker = False
            self.emergency = False
        if enemiesCloseToTh.amount > army_count and not self.expanding and not self.panic:
            self.stop_worker = True
            self.emergency = True

    async def check_cannon(self):
        for th in self.townhalls:
            if self.known_enemy_structures.closer_than(15, th.position) and not self.cannon_rush and self.get_game_time() < 240:
                self.stop_expand = True
                self.stop_worker = True
                self.attack_supply = 50
                self.cannon_rush = True
                print(self.attack_supply)
                print(self.stop_worker)
                await self.chat_send("(probe) (pylon) (cannon)")
                for h in self.townhalls:
                    if CANCEL in await self.get_available_abilities(h):
                        await self.do(h(CANCEL))

            #elif self.known_enemy_structures.closer_than(30, th.position) and self.cannon_rush:
            #    self.stop_expand = False
            #    self.stop_worker = False
            #    self.attack_supply = 193
            #    self.cannon_rush = False

    async def scout(self):
        scout = None

        # Check if we already have a scout (a worker with PATROL order)
        for worker in self.workers:
            if self.has_order([PATROL], worker):
                scout = worker

        if not scout and self.get_game_time() < 180:
            random_exp_location = random.choice(self.enemy_start_locations)
            scout = self.workers.closest_to(self.start_location)

            if not scout:
                return

            await self.order(scout, PATROL, random_exp_location)
            return

        # If we don't have a scout, select one, and order it to move to random exp
        if not scout:
            random_exp_location = random.choice(list(self.expansion_locations.keys()))
            scout = self.workers.closest_to(self.start_location)

            if not scout:
                return

            await self.order(scout, PATROL, random_exp_location)
            return

        # Basic avoidance: If enemy is too close, go to map center
        nearby_enemy_units = self.known_enemy_units.filter(lambda unit: unit.type_id not in self.units_to_ignore).closer_than(10, scout)
        if nearby_enemy_units.exists:
            await self.order(scout, PATROL, self.game_info.map_center)
            return

        # We're close enough, so change target
        target = sc2.position.Point2((scout.orders[0].target.x, scout.orders[0].target.y))
        if scout.distance_to(target) < 10:
            random_exp_location = random.choice(list(self.expansion_locations.keys()))
            await self.order(scout, PATROL, random_exp_location)
            return

    async def attack(self):
        army_units = self.units(ROACH).ready | self.units(HYDRALISK).ready | self.units(OVERSEER).ready | self.units(MUTALISK).ready | self.units(ZERGLING).ready | self.units(BANELING).ready
        army_idle = army_units.idle
        for unit in army_idle:
            if self.supply_used > self.attack_supply and not self.defending and not self.cannon_rush:
                await self.do(unit.attack(self.find_target(self.state).position))
                self.hive_tech = True
                self.attacking = True
            elif self.cannon_rush:
                if not self.move:
                    await self.do(unit.move(self.game_info.map_center))
                    self.move = True
                    self.attacking = True
                if self.move:
                    for unit in army_idle:
                        random_exp_location = random.choice(list(self.expansion_locations.keys()))
                        await self.do(unit.attack(random_exp_location))

            elif self.supply_used < (self.attack_supply - 50):
                self.attacking = False

    async def upgrade_flyer(self):
        if self.units(SPIRE).exists:
            evochamber = self.units(SPIRE).first
            if self.strategy == "muta/ling/bane":
            # Only if we're not upgrading anything yet
                if evochamber.noqueue:
            # Go through each weapon, armor and shield upgrade and check if we can research it, and if so, do it
                    for upgrade_level in range(1, 4):
                        upgrade_armor_id = getattr(sc2.constants, "RESEARCH_ZERGFLYERATTACKLEVEL" + str(upgrade_level))
                        upgrade_missle_id = getattr(sc2.constants, "RESEARCH_ZERGFLYERARMORLEVEL" + str(upgrade_level))
                        if await self.has_ability(upgrade_missle_id, evochamber):
                            if self.can_afford(upgrade_missle_id):
                                await self.do(evochamber(upgrade_missle_id))
                        elif await self.has_ability(upgrade_armor_id, evochamber):
                            if self.can_afford(upgrade_armor_id):
                                await self.do(evochamber(upgrade_armor_id))

    async def build_muta_ling(self):
        army_count = self.units(ROACH).amount | self.units(HYDRALISK).amount | self.units(OVERSEER).amount | self.units(MUTALISK).amount | self.units(ZERGLING).amount | self.units(BANELING).amount
        if self.units(SPIRE).exists or self.already_pending(SPIRE) or self.emergency or self.panic:
            if army_count > 1:
                if (self.units(MUTALISK).amount / army_count) < 0.5 and self.units(SPIRE).ready.exists:
                    await self.build_muta()
                else:
                    await self.build_zerglings()
            else:
                await self.build_zerglings()

    async def build_muta(self):
        larvae = self.units(LARVA)
        if self.can_afford(SPIRE) and larvae.exists and self.townhalls.amount > 2:
            larva = larvae.random
            await self.do(larva.train(MUTALISK))

    async def spire(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if (self.units(LAIR).exists or self.units(HIVE).exists) and not self.already_pending(SPIRE) and not self.units(SPIRE).exists:         
            if self.can_afford(SPIRE):
                await self.build(SPIRE, near=hq.position.towards(self.game_info.map_center, 8))

    async def rolly_polly(self):
        if self.vespene >= 100:
            bn = self.units(BANELINGNEST).ready
            if bn.exists and self.minerals >= 100 and self.units(LAIR).exists:
                await self.do(bn.first(RESEARCH_CENTRIFUGALHOOKS))

    async def build_banes(self):
        for ling in self.units(ZERGLING).ready:
            if self.units(ZERGLING).amount > 1 and self.units(BANELINGNEST).exists and not self.attacking and not self.defending:
                if (self.units(BANELING).amount / self.units(ZERGLING).amount) < 0.5:
                    await self.do(ling(MORPHZERGLINGTOBANELING_BANELING))

    async def build_banenest(self):
        hqr = self.townhalls.ready
        if hqr.exists:
            hq = self.townhalls.random
        if self.units(SPAWNINGPOOL).exists and not self.already_pending(BANELINGNEST) and not self.units(BANELINGNEST).exists:         
            if self.can_afford(BANELINGNEST):
                await self.build(BANELINGNEST, near=hq.position.towards(self.game_info.map_center, 8))

    async def build_hydra_ling(self):
        army_count = self.units(ROACH).amount | self.units(HYDRALISK).amount | self.units(OVERSEER).amount | self.units(MUTALISK).amount | self.units(ZERGLING).amount | self.units(BANELING).amount
        if self.units(HYDRALISKDEN).exists or self.emergency:
            if army_count > 1:
                if (self.units(HYDRALISK).amount / army_count) < 0.2 and self.units(HYDRALISKDEN).ready.exists:
                    await self.build_hydra()
                else:
                    await self.build_zerglings()
            else:
                await self.build_zerglings()
        elif self.panic or self.emergency: 
            await self.build_zerglings()
    async def metabolic_boost(self):
        if self.vespene >= 100:
            sp = self.units(SPAWNINGPOOL).ready
            if sp.exists and self.minerals >= 100 and not self.mboost_started:
                await self.do(sp.first(RESEARCH_ZERGLINGMETABOLICBOOST))
                if not sp.noqueue:
                    self.mboost_started = True

    async def defend(self):
        army_units = self.units(ROACH).ready | self.units(HYDRALISK).ready | self.units(OVERSEER).ready | self.units(MUTALISK).ready | self.units(ZERGLING).ready | self.units(BANELING).ready
        enemiesCloseToTh = None
        for th in self.townhalls:
            enemiesCloseToTh = self.known_enemy_units.closer_than(self.defendRangeToTownhalls, th.position)
        if enemiesCloseToTh and not self.cannon_rush and not self.attacking:
            for unit in army_units:
                await self.do(unit.attack(enemiesCloseToTh.random.position))
                self.defending = True
        elif not enemiesCloseToTh:
            self.defending = False

    async def attack_rally_location(self):
        army_units = self.units(ROACH).ready | self.units(HYDRALISK).ready | self.units(OVERSEER).ready | self.units(MUTALISK).ready | self.units(ZERGLING).ready | self.units(BANELING).ready        
        for unit in army_units:
            if not self.attacking and not self.defending:
                attack_location = self.get_rally_location()
                await self.do(unit.attack(attack_location))

    async def hasLair(self):
        if(self.units(LAIR).amount > 0):
            return True
        morphingYet = False
        for h in self.units(HATCHERY):
            if CANCEL_MORPHLAIR in await self.get_available_abilities(h):
                morphingYet = True
                break
        if morphingYet:
            return True
        return False

    async def queen_micro(self):
        if self.units(QUEEN).exists and self.defending_queens:
            queen = self.units(QUEEN).filter(lambda x:x.energy >= 50)
            transfuseTargets = self.units.filter(lambda x: x.type_id in [QUEEN] and (x.health_max - x.health >= 125 or x.health / x.health_max < 1/4))
            if transfuseTargets != None:
                for q in queen:
                    transfuseTarget = transfuseTargets.closest_to(q)
                    if transfuseTarget.distance_to(q) < 7: # replace with general queen transfuse range
                        abilities = await self.get_available_abilities(q)
                        if AbilityId.TRANSFUSION_TRANSFUSION in abilities and self.can_afford(TRANSFUSION_TRANSFUSION):
                            transfuseTargets = transfuseTargets.filter(lambda x:x.tag not in targetsBeingTransfusedTags)
                            await self.do(q(TRANSFUSION_TRANSFUSION, transfuseTarget))

    async def defend_queens(self):
        army_units = self.units(QUEEN).ready
        enemiesCloseToTh = None
        for th in self.townhalls:
            enemiesCloseToTh = self.known_enemy_units.closer_than(15, th.position)
        if not enemiesCloseToTh:
            self.defending_queens = False
        elif enemiesCloseToTh and not self.cannon_rush:
            for unit in army_units:
                await self.do(unit.attack(enemiesCloseToTh.random.position))
                self.defending_queens = True

    async def set_rally_hatchery(self):

        rally_location = self.get_rally_location()
        for hatch in self.units(HATCHERY).ready:
            await self.do(hatch(RALLY_BUILDING, rally_location))

    async def set_rally_lair(self):

        rally_location = self.get_rally_location()
        for lair in self.units(LAIR).ready:
            await self.do(lair(RALLY_BUILDING, rally_location))

    async def set_rally_hive(self):

        rally_location = self.get_rally_location()
        for hive in self.units(HIVE).ready:
            await self.do(hive(RALLY_BUILDING, rally_location))

    async def build_roach_hydra(self):
        army_count = self.units(ROACH).amount | self.units(HYDRALISK).amount | self.units(OVERSEER).amount | self.units(MUTALISK).amount | self.units(ZERGLING).amount | self.units(BANELING).amount
        if army_count > 0.5:
            if (self.units(ROACH).amount / army_count) < 0.5 and self.units(ROACHWARREN).ready.exists:
                await self.build_roach()
        elif army_count > 0.5:
            if (self.units(HYDRALISK).amount / army_count) < 0.5 and self.units(HYDRALISKDEN).ready.exists:
                await self.build_hydra()
        else:
            await self.build_zerglings()

    async def build_zerglings(self):
        larvae = self.units(LARVA)
        if self.can_afford(ZERGLING) and larvae.exists and not self.stop_army:
            larva = larvae.random
            await self.do(larva.train(ZERGLING))

    async def upgrade_hydra_speed(self):
        hd = self.units(HYDRALISKDEN).ready
        if not self.maug_started and hd.noqueue:
            if self.vespene >= 100:
                if hd.exists and self.minerals >= 100:
                    await self.do(hd.first(RESEARCH_MUSCULARAUGMENTS))
                    if not hd.noqueue:
                        self.maug_started = True
    
    async def upgrade_hydra_range(self):
        hd = self.units(HYDRALISKDEN).ready
        if not self.gspines_started and hd.noqueue:
            if self.vespene >= 100:
                if hd.exists and self.minerals >= 100:
                    await self.do(hd.first(RESEARCH_GROOVEDSPINES))
                    if not hd.noqueue:
                        self.gspines_started = True

    async def hydra_den(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if (self.units(LAIR).exists or self.units(HIVE).exists) and not self.already_pending(HYDRALISKDEN) and not self.units(HYDRALISKDEN).exists:         
            if self.can_afford(HYDRALISKDEN):
                await self.build(HYDRALISKDEN, near=hq.position.towards(self.game_info.map_center, 8))

    async def build_hydra(self):
        larvae = self.units(LARVA)
        if self.can_afford(HYDRALISK) and larvae.exists and self.townhalls.amount > 2:
            larva = larvae.random
            await self.do(larva.train(HYDRALISK))

    async def upgrade_roach(self):
        rw = self.units(ROACHWARREN).ready
        if not self.grecon_started and (self.units(LAIR).exists or self.units(HIVE).exists) and not self.already_pending(LAIR) and rw.noqueue:
            if self.vespene >= 100:
                if rw.exists and self.minerals >= 100:
                    await self.do(rw.first(RESEARCH_GLIALREGENERATION))
                    if not rw.noqueue: 
                        self.grecon_started = True

    async def upgrade(self):
        if self.units(EVOLUTIONCHAMBER).exists:
            evochamber = self.units(EVOLUTIONCHAMBER).first
            if self.strategy == "muta/ling/bane":
            # Only if we're not upgrading anything yet
                if evochamber.noqueue:
            # Go through each weapon, armor and shield upgrade and check if we can research it, and if so, do it
                    for upgrade_level in range(1, 4):
                        upgrade_armor_id = getattr(sc2.constants, "RESEARCH_ZERGGROUNDARMORLEVEL" + str(upgrade_level))
                        upgrade_missle_id = getattr(sc2.constants, "RESEARCH_ZERGMELEEWEAPONSLEVEL" + str(upgrade_level))
                        if await self.has_ability(upgrade_missle_id, evochamber):
                            if self.can_afford(upgrade_missle_id):
                                await self.do(evochamber(upgrade_missle_id))
                        elif await self.has_ability(upgrade_armor_id, evochamber):
                            if self.can_afford(upgrade_armor_id):
                                await self.do(evochamber(upgrade_armor_id))

            elif self.strategy == "hydra/ling/bane":
                if evochamber.noqueue:
                    for upgrade_level in range(1, 4):
                        upgrade_armor_id = getattr(sc2.constants, "RESEARCH_ZERGGROUNDARMORLEVEL" + str(upgrade_level))
                        upgrade_missle_id = getattr(sc2.constants, "RESEARCH_ZERGMISSILEWEAPONSLEVEL" + str(upgrade_level))
                        upgrade_melee_id = getattr(sc2.constants, "RESEARCH_ZERGMELEEWEAPONSLEVEL" + str(upgrade_level))
                        if await self.has_ability(upgrade_missle_id, evochamber):
                            if self.can_afford(upgrade_missle_id):
                                await self.do(evochamber(upgrade_missle_id))
                        elif await self.has_ability(upgrade_armor_id, evochamber):
                            if self.can_afford(upgrade_armor_id):
                                await self.do(evochamber(upgrade_armor_id))
                        elif await self.has_ability(upgrade_melee_id, evochamber):
                            if self.can_afford(upgrade_melee_id):
                                await self.do(evochamber(upgrade_melee_id))
 
            if self.strategy == "roach/hydra" or self.strategy == "hydra":
            # Only if we're not upgrading anything yet
                if evochamber.noqueue:
            # Go through each weapon, armor and shield upgrade and check if we can research it, and if so, do it
                    for upgrade_level in range(1, 4):
                        upgrade_armor_id = getattr(sc2.constants, "RESEARCH_ZERGGROUNDARMORLEVEL" + str(upgrade_level))
                        upgrade_missle_id = getattr(sc2.constants, "RESEARCH_ZERGMISSILEWEAPONSLEVEL" + str(upgrade_level))
                        if await self.has_ability(upgrade_missle_id, evochamber):
                            if self.can_afford(upgrade_missle_id):
                                await self.do(evochamber(upgrade_missle_id))
                        elif await self.has_ability(upgrade_armor_id, evochamber):
                            if self.can_afford(upgrade_armor_id):
                                await self.do(evochamber(upgrade_armor_id))

    async def research_burrow(self):
        #print(self.burrow_started)
        hatch = self.units(HATCHERY).ready
        if not self.burrow_started and hatch.noqueue:
            if hatch.exists and self.vespene >= 100:
                if self.minerals >= 100:
                    await self.do(hatch.first(RESEARCH_BURROW))
                    if not hatch.noqueue:
                        self.burrow_started = True

    async def roach_micro(self):
        for roach in self.units(ROACH):
            # burrow when low hp
            if roach.health / roach.health_max < 5/10:
                abilities = await self.get_available_abilities(roach)
                if AbilityId.BURROWDOWN_ROACH in abilities and self.can_afford(BURROWDOWN_ROACH):
                    await self.do(roach(BURROWDOWN_ROACH))

        for roach in self.units(ROACHBURROWED):
            if 9/10 <= roach.health / roach.health_max <= 2 and roach.is_burrowed:
                abilities = await self.get_available_abilities(roach)
                # print(abilities)
                if AbilityId.BURROWUP_ROACH in abilities and self.can_afford(BURROWUP_ROACH):
                    await self.do(roach(BURROWUP_ROACH))

    async def roach_warren(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if self.units(SPAWNINGPOOL).exists and not self.already_pending(ROACHWARREN) and not self.units(ROACHWARREN).exists:         
            if self.can_afford(ROACHWARREN):
                await self.build(ROACHWARREN, near=hq.position.towards(self.game_info.map_center, 8))

    async def build_roach(self):
        larvae = self.units(LARVA)
        if self.can_afford(ROACH) and larvae.exists and self.townhalls.amount > 2:
            larva = larvae.random
            await self.do(larva.train(ROACH))

    def assignQueen(self, maxAmountInjectQueens=5):
        # # list of all alive queens and bases, will be used for injecting
        if not hasattr(self, "queensAssignedHatcheries"):
            self.queensAssignedHatcheries = {}

        if maxAmountInjectQueens == 0:
            self.queensAssignedHatcheries = {}

        # if queen is done, move it to the closest hatch/lair/hive that doesnt have a queen assigned
        queensNoInjectPartner = self.units(QUEEN).filter(lambda q: q.tag not in self.queensAssignedHatcheries.keys())
        basesNoInjectPartner = self.townhalls.filter(lambda h: h.tag not in self.queensAssignedHatcheries.values() and h.build_progress > 0.8)

        for queen in queensNoInjectPartner:                          
            if basesNoInjectPartner.amount == 0:
                break
            closestBase = basesNoInjectPartner.closest_to(queen)
            self.queensAssignedHatcheries[queen.tag] = closestBase.tag
            basesNoInjectPartner = basesNoInjectPartner - [closestBase]
            break # else one hatch gets assigned twice


    async def doQueenInjects(self, iteration):
        # list of all alive queens and bases, will be used for injecting
        aliveQueenTags = [queen.tag for queen in self.units(QUEEN)] # list of numbers (tags / unit IDs)
        aliveBasesTags = [base.tag for base in self.townhalls]

        # make queens inject if they have 25 or more energy
        toRemoveTags = []

        if hasattr(self, "queensAssignedHatcheries"):
            for queenTag, hatchTag in self.queensAssignedHatcheries.items():
                # queen is no longer alive
                if queenTag not in aliveQueenTags: 
                    toRemoveTags.append(queenTag)
                    continue
                # hatchery / lair / hive is no longer alive
                if hatchTag not in aliveBasesTags:
                    toRemoveTags.append(queenTag)
                    continue
                # queen and base are alive, try to inject if queen has 25+ energy
                queen = self.units(QUEEN).find_by_tag(queenTag)            
                hatch = self.townhalls.find_by_tag(hatchTag)            
                if hatch.is_ready:
                    if queen.energy >= 25 and queen.is_idle and not hatch.has_buff(QUEENSPAWNLARVATIMER) and not self.defending_queens:
                        await self.do(queen(EFFECT_INJECTLARVA, hatch))
                else:
                    if iteration % self.injectInterval == 0 and queen.is_idle and queen.position.distance_to(hatch.position) > 10 and not self.defending_queens:
                        await self.do(queen(AbilityId.MOVE, hatch.position.to2))

            # clear queen tags (in case queen died or hatch got destroyed) from the dictionary outside the iteration loop
            for tag in toRemoveTags:
                self.queensAssignedHatcheries.pop(tag)

    async def build_queens(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.first
        if self.units(SPAWNINGPOOL).ready.exists:
            if self.units(QUEEN).amount < (((self.units(HATCHERY).amount) + (self.units(LAIR).amount) + (self.units(HIVE).amount)) * 1.25) and hq.is_ready and hq.noqueue:
                if self.can_afford(QUEEN) and not self.already_pending(QUEEN) and self.units(QUEEN).amount < 10:
                    await self.do(hq.train(QUEEN))

    async def build_extractor(self):
        if self.townhalls.exists:
            hq = self.townhalls.random
        hqa = self.townhalls.amount
        
        if (self.strategy == "roach/hydra" or self.strategy == "hydra/ling/bane" or self.strategy == "hydra") and self.townhalls.exists:
            vaspenes = self.state.vespene_geyser.closer_than(15.0, hq)
            if hqa < 6:
                if not self.already_pending(EXTRACTOR) and (self.units(EXTRACTOR).amount / (self.townhalls.amount * 1.25)) < 1:
                    for vaspene in vaspenes:
                        if not self.can_afford(EXTRACTOR):
                            break
                        worker = self.select_build_worker(vaspene.position)
                        if worker is None:
                            break
                        if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                            await self.do(worker.build(EXTRACTOR, vaspene))
            elif hqa > 5:
                if not self.already_pending(EXTRACTOR):
                    for vaspene in vaspenes:
                        if not self.can_afford(EXTRACTOR):
                            break
                        worker = self.select_build_worker(vaspene.position)
                        if worker is None:
                            break
                        if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                            await self.do(worker.build(EXTRACTOR, vaspene))

        elif self.strategy == "muta/ling/bane" and self.townhalls.exists:
            vaspenes = self.state.vespene_geyser.closer_than(15.0, hq)
            if not self.already_pending(EXTRACTOR):
                    for vaspene in vaspenes:
                        if not self.can_afford(EXTRACTOR):
                            break
                        worker = self.select_build_worker(vaspene.position)
                        if worker is None:
                            break
                        if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                            await self.do(worker.build(EXTRACTOR, vaspene))

    async def build_evochamber(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if self.units(LAIR).exists or self.units(HIVE).exists:
            if self.can_afford(EVOLUTIONCHAMBER) and self.already_pending(EVOLUTIONCHAMBER) < 2 and self.units(EVOLUTIONCHAMBER).amount < 2:
                await self.build(EVOLUTIONCHAMBER, near=hq.position.towards(self.game_info.map_center, 8))

    async def build_spawning_pool(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if not (self.units(SPAWNINGPOOL).exists or self.already_pending(SPAWNINGPOOL)):
            if self.can_afford(SPAWNINGPOOL) and not self.stop_worker:
                await self.build(SPAWNINGPOOL, near=hq.position.towards(self.game_info.map_center, 8))

    async def upgrade_hatch(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if self.units(SPAWNINGPOOL).ready.exists and not await self.hasLair() and not self.units(HIVE).exists and self.units(HATCHERY).exists:
            if self.can_afford(GHOST):
                await self.do(hq.build(LAIR))

    async def upgrade_lair(self):
        hqe = self.townhalls.ready
        if hqe.exists:
            hq = self.townhalls.random
        if self.units(LAIR).ready.exists and not self.units(HIVE).exists and not self.already_pending(HIVE):
            if self.can_afford(THOR):
                await self.do(hq.build(HIVE))
                
    async def updateCreepCoverage(self, stepSize=None):
        if stepSize is None:
            stepSize = self.creepTargetDistance
        ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]

        positions = [Point2((x, y)) \
        for x in range(self._game_info.playable_area[0]+stepSize, self._game_info.playable_area[0] + self._game_info.playable_area[2]-stepSize, stepSize) \
        for y in range(self._game_info.playable_area[1]+stepSize, self._game_info.playable_area[1] + self._game_info.playable_area[3]-stepSize, stepSize)]

        validPlacements = await self._client.query_building_placement(ability, positions)
        successResults = [
            ActionResult.Success, # tumor can be placed there, so there must be creep
            ActionResult.CantBuildLocationInvalid, # location is used up by another building or doodad,
            ActionResult.CantBuildTooFarFromCreepSource, # - just outside of range of creep            
            # ActionResult.CantSeeBuildLocation - no vision here      
            ]
        # self.positionsWithCreep = [p for index, p in enumerate(positions) if validPlacements[index] in successResults]
        self.positionsWithCreep = [p for valid, p in zip(validPlacements, positions) if valid in successResults]
        self.positionsWithoutCreep = [p for index, p in enumerate(positions) if validPlacements[index] not in successResults]
        self.positionsWithoutCreep = [p for valid, p in zip(validPlacements, positions) if valid not in successResults]
        return self.positionsWithCreep, self.positionsWithoutCreep


    async def doCreepSpread(self):
        # only use queens that are not assigned to do larva injects
        allTumors = self.units(CREEPTUMOR) | self.units(CREEPTUMORBURROWED) | self.units(CREEPTUMORQUEEN)

        if not hasattr(self, "usedCreepTumors"):
            self.usedCreepTumors = set()

        # gather all queens that are not assigned for injecting and have 25+ energy
        if hasattr(self, "queensAssignedHatcheries"):
            unassignedQueens = self.units(QUEEN).filter(lambda q: (q.tag not in self.queensAssignedHatcheries and q.energy >= 50) and (q.is_idle or len(q.orders) == 1 and q.orders[0].ability.id in [AbilityId.MOVE]))
        else:
            unassignedQueens = self.units(QUEEN).filter(lambda q: q.energy >= 50 and (q.is_idle or len(q.orders) == 1 and q.orders[0].ability.id in [AbilityId.MOVE]))

        # update creep coverage data and points where creep still needs to go
        if not hasattr(self, "positionsWithCreep") or self.iteration % self.creepSpreadInterval * 10 == 0:
            posWithCreep, posWithoutCreep = await self.updateCreepCoverage()
            totalPositions = len(posWithCreep) + len(posWithoutCreep)
            self.creepCoverage = len(posWithCreep) / totalPositions
            # print(self.getTimeInSeconds(), "creep coverage:", creepCoverage)

        # filter out points that have already tumors / bases near them
        if hasattr(self, "positionsWithoutCreep"):
            self.positionsWithoutCreep = [x for x in self.positionsWithoutCreep if (allTumors | self.townhalls).closer_than(self.creepTargetCountsAsReachedDistance, x).amount < 1 or (allTumors | self.townhalls).closer_than(self.creepTargetCountsAsReachedDistance + 10, x).amount < 5] # have to set this to some values or creep tumors will clump up in corners trying to get to a point they cant reach

        # make all available queens spread creep until creep coverage is reached 50%
        if hasattr(self, "creepCoverage") and (self.creepCoverage < self.stopMakingNewTumorsWhenAtCoverage or allTumors.amount - len(self.usedCreepTumors) < 25):
            for queen in unassignedQueens:
                # locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=queen, minRange=3, maxRange=30, stepSize=2, locationAmount=16)
                if self.townhalls.ready.exists and not self.defending_queens:
                    locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=queen, minRange=3, maxRange=30, stepSize=2, locationAmount=16)
                    # locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=self.townhalls.ready.random, minRange=3, maxRange=30, stepSize=2, locationAmount=16)
                    if locations is not None:
                        for loc in locations:
                            err = await self.do(queen(BUILD_CREEPTUMOR_QUEEN, loc))
                            if not err:
                                break

        
        unusedTumors = allTumors.filter(lambda x: x.tag not in self.usedCreepTumors)
        tumorsMadeTumorPositions = set()
        for tumor in unusedTumors:
            tumorsCloseToTumor = [x for x in tumorsMadeTumorPositions if tumor.distance_to(Point2(x)) < 8]
            if len(tumorsCloseToTumor) > 0:
                continue
            abilities = await self.get_available_abilities(tumor)
            if AbilityId.BUILD_CREEPTUMOR_TUMOR in abilities:
                locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=tumor, minRange=10, maxRange=10) # min range could be 9 and maxrange could be 11, but set both to 10 and performance is a little better
                if locations is not None:
                    for loc in locations:
                        err = await self.do(tumor(BUILD_CREEPTUMOR_TUMOR, loc))
                        if not err:
                            tumorsMadeTumorPositions.add((tumor.position.x, tumor.position.y))
                            self.usedCreepTumors.add(tumor.tag)
                            break

    async def find_strategy(self):
        if self.enemy_race != None and self.strategy == "Unsure":
            if self.enemy_race == "Terran":
                self.strategy = "hydra/ling/bane"
            elif self.enemy_race == "Zerg":
                self.strategy = "roach/hydra"
            elif self.enemy_race == "Protoss":
                self.strategy = "muta/ling/bane"

            await self.chat_send("Going " + self.strategy)

    async def find_race(self):
        if self.known_enemy_units.amount > 0 and self.enemy_race == None:
            enemy_units = self.remembered_enemy_units
            if self.remembered_enemy_units.filter(lambda unit: unit.type_id in self.Terran):
                self.enemy_race = "Terran"
            elif self.remembered_enemy_units.filter(lambda unit: unit.type_id in self.Zerg):
                self.enemy_race = "Zerg"
            elif self.remembered_enemy_units.filter(lambda unit: unit.type_id in self.Protoss):
                self.enemy_race = "Protoss"

            await self.chat_send("Facing " + self.enemy_race)

                
    async def expand(self):
        expand_every = 2 * 60
        prefered_base_count = 1 + int(math.floor(self.get_game_time() / expand_every))
        prefered_base_count = max(prefered_base_count, 2) # Take natural ASAP (i.e. minimum 2 bases)
        current_base_count = (self.units(HATCHERY).amount + self.units(LAIR).amount + self.units(HIVE).amount)

        if self.minerals > 900:
            prefered_base_count += 1

        if current_base_count < prefered_base_count and not self.stop_expand and not self.defending and not self.panic and not self.emergency:
            self.stop_worker = True
            self.stop_army = True
            self.expanding = True
            if self.can_afford(HATCHERY) and current_base_count < 8:
                    location = await self.get_next_expansion()
                    location = await self.find_placement(HATCHERY, near=location, random_alternative=False, placement_step=1, minDistanceToResources=5)
                    if location is not None:
                        w = self.select_build_worker(location)
                        if w is not None:
                            err = await self.build(HATCHERY, location, max_distance=20, unit=w, random_alternative=False, placement_step=1)

        elif (current_base_count >= prefered_base_count or self.already_pending(HATCHERY)) and not self.cannon_rush and not self.panic and not self.emergency:
            self.stop_worker = False
            self.stop_army = False
            self.expanding = False

    async def build_workers(self):
        larvae = self.units(LARVA)
        if len(((self.units(HATCHERY))*22) + ((self.units(LAIR))*22) + ((self.units(HIVE))*22)) > len(self.units(DRONE)) and not self.stop_worker:
            if self.units(DRONE).amount > 40:
                if self.can_afford(DRONE) and larvae.exists and self.already_pending(DRONE) < 2 and self.units(DRONE).amount < 80:
                    larva = larvae.random
                    await self.do(larva.train(DRONE))
            else:
                if self.can_afford(DRONE) and larvae.exists and (self.units(DRONE).amount) < 80:
                    larva = larvae.random
                    await self.do(larva.train(DRONE))

    async def build_overlords(self):
        larvae = self.units(LARVA)
        if self.supply_used < 195:    
            if self.supply_left < 7 and larvae.exists and self.already_pending(OVERLORD) < 2:
                if self.can_afford(OVERLORD):
                    larva = larvae.random
                    await self.do(larva.train(OVERLORD))

        if (self.units(LAIR) | self.units(HIVE)).exists and (self.units(OVERSEER) | self.units(OVERLORDCOCOON)).amount < 2 and not self.stop_army:
                if self.units(OVERLORD).exists and self.can_afford(OVERSEER):
                        ov = self.units(OVERLORD).random
                        await self.do(ov(MORPH_OVERSEER))

    async def ov_scout(self):
        #if len(self.enemy_start_locations) > 1:
            #print(self.enemy_start_locations)
        #    if self.units(OVERLORD).amount > 3:
        #        ov1 = self.units(OVERLORD).idle.closest_to(self.enemy_start_locations[0])
        #        if not self.ov1_scout and ov1:
        #            await self.do(ov1.move(self.enemy_start_locations[0].position))
        #            self.ov1_scout = True
        #        ov2 = self.units(OVERLORD).idle.closest_to(self.enemy_start_locations[1])
        #        if not self.ov2_scout and ov2:
        #            await self.do(ov2.move(self.enemy_start_locations[1].position))
        #            self.ov2_scout = True
        #        ov3 = self.units(OVERLORD).idle.closest_to(self.enemy_start_locations[2])
        #        if not self.ov3_scout and ov3:
        #            await self.do(ov3.move(self.enemy_start_locations[2].position))
        #            self.ov3_scout = True
        #else:
        ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
        if not self.ovy_scout:
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.ovy_scout = True

    def get_game_time(self):

        return self.state.game_loop*0.725*(1/16)

    def get_rally_location(self):
        if self.townhalls.exists:
            hq = self.townhalls.closest_to(self.game_info.map_center).position
            rally_location = hq.position.towards(self.game_info.map_center, 8)
            return rally_location

    def find_target(self, state):
        if len(self.known_enemy_units) > 0:
            return random.choice(self.known_enemy_units)
        elif len(self.known_enemy_structures) > 0:
            return random.choice(self.known_enemy_structures)
        else:
            return self.enemy_start_locations[0]

    async def do(self, action):
        
        self.order_queue.append(action) #await self._client.actions(action, game_data=self._game_data)

    async def execute_order_queue(self):
        await self._client.actions(self.order_queue, game_data=self._game_data)
        self.order_queue = [] # Reset order queue

    async def has_ability(self, ability, unit):
        abilities = await self.get_available_abilities(unit)
        if ability in abilities:
            return True
        else:
            return False

    async def can_take_expansion(self):
        # Must have a valid exp location
        location = await self.get_next_expansion()
        if not location:
            return False
        # Must be able to find a valid building position
        if self.can_afford(HATCHERY):
            position = await self.find_placement(HATCHERY, location.rounded, max_distance=10, random_alternative=False, placement_step=1)
            if not position:
                return False

        return True
    
    async def find_placement(self, building, near, max_distance=20, random_alternative=False, placement_step=3, min_distance=0, minDistanceToResources=3):
        """Finds a placement location for building."""

        assert isinstance(building, (AbilityId, UnitTypeId))
        # assert self.can_afford(building)
        assert isinstance(near, Point2)

        if isinstance(building, UnitTypeId):
            building = self._game_data.units[building.value].creation_ability
        else: # AbilityId
            building = self._game_data.abilities[building.value]

        if await self.can_place(building, near):
            return near

        for distance in range(min_distance, max_distance, placement_step):
            possible_positions = [Point2(p).offset(near).to2 for p in (
                [(dx, -distance) for dx in range(-distance, distance+1, placement_step)] +
                [(dx,  distance) for dx in range(-distance, distance+1, placement_step)] +
                [(-distance, dy) for dy in range(-distance, distance+1, placement_step)] +
                [( distance, dy) for dy in range(-distance, distance+1, placement_step)]
            )]
            if (self.townhalls | self.state.mineral_field | self.state.vespene_geyser).exists and minDistanceToResources > 0: 
                possible_positions = [x for x in possible_positions if (self.state.mineral_field | self.state.vespene_geyser).closest_to(x).distance_to(x) >= minDistanceToResources] # filter out results that are too close to resources

            res = await self._client.query_building_placement(building, possible_positions)
            possible = [p for r, p in zip(res, possible_positions) if r == ActionResult.Success]
            if not possible:
                continue

            if random_alternative:
                return random.choice(possible)
            else:
                return min(possible, key=lambda p: p.distance_to(near))
        return None

    async def findCreepPlantLocation(self, targetPositions, castingUnit, minRange=None, maxRange=None, stepSize=1, onlyAttemptPositionsAroundUnit=False, locationAmount=32, dontPlaceTumorsOnExpansions=True):
        """function that figures out which positions are valid for a queen or tumor to put a new tumor     
        
        Arguments:
            targetPositions {set of Point2} -- For me this parameter is a set of Point2 objects where creep should go towards 
            castingUnit {Unit} -- The casting unit (queen or tumor)
        
        Keyword Arguments:
            minRange {int} -- Minimum range from the casting unit's location (default: {None})
            maxRange {int} -- Maximum range from the casting unit's location (default: {None})
            onlyAttemptPositionsAroundUnit {bool} -- if True, it will only attempt positions around the unit (ideal for tumor), if False, it will attempt a lot of positions closest from hatcheries (ideal for queens) (default: {False})
            locationAmount {int} -- a factor for the amount of positions that will be attempted (default: {50})
            dontPlaceTumorsOnExpansions {bool} -- if True it will sort out locations that would block expanding there (default: {True})
        
        Returns:
            list of Point2 -- a list of valid positions to put a tumor on
        """

        assert isinstance(castingUnit, Unit)
        positions = []
        ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]
        if minRange is None: minRange = 0
        if maxRange is None: maxRange = 500

        # get positions around the casting unit
        positions = self.getPositionsAroundUnit(castingUnit, minRange=minRange, maxRange=maxRange, stepSize=stepSize, locationAmount=locationAmount)

        # stop when map is full with creep
        if len(self.positionsWithoutCreep) == 0:
            return None

        # filter positions that would block expansions
        if dontPlaceTumorsOnExpansions and hasattr(self, "exactExpansionLocations"):
            positions = [x for x in positions if self.getHighestDistance(x.closest(self.exactExpansionLocations), x) > 3] 
            # TODO: need to check if this doesnt have to be 6 actually
            # this number cant also be too big or else creep tumors wont be placed near mineral fields where they can actually be placed

        # check if any of the positions are valid
        validPlacements = await self._client.query_building_placement(ability, positions)

        # filter valid results
        validPlacements = [p for index, p in enumerate(positions) if validPlacements[index] == ActionResult.Success]

        allTumors = self.units(CREEPTUMOR) | self.units(CREEPTUMORBURROWED) | self.units(CREEPTUMORQUEEN)
        # usedTumors = allTumors.filter(lambda x:x.tag in self.usedCreepTumors)
        unusedTumors = allTumors.filter(lambda x:x.tag not in self.usedCreepTumors)
        if castingUnit is not None and castingUnit in allTumors:
            unusedTumors = unusedTumors.filter(lambda x:x.tag != castingUnit.tag)

        # filter placements that are close to other unused tumors
        if len(unusedTumors) > 0:
            validPlacements = [x for x in validPlacements if x.distance_to(unusedTumors.closest_to(x)) >= 10] 

        validPlacements.sort(key=lambda x: x.distance_to(x.closest(self.positionsWithoutCreep)), reverse=False)

        if len(validPlacements) > 0:
            return validPlacements
        return None

    async def findExactExpansionLocations(self):
        # execute this on start, finds all expansions where creep tumors should not be build near
        self.exactExpansionLocations = []
        for loc in self.expansion_locations.keys():
            self.exactExpansionLocations.append(await self.find_placement(HATCHERY, loc, minDistanceToResources=5.5, placement_step=1)) # TODO: change mindistancetoresource so that a hatch still has room to be built

    def getPositionsAroundUnit(self, unit, minRange=0, maxRange=500, stepSize=1, locationAmount=32):
        # e.g. locationAmount=4 would only consider 4 points: north, west, east, south
        assert isinstance(unit, (Unit, Point2, Point3))
        if isinstance(unit, Unit):
            loc = unit.position.to2
        else:
            loc = unit
        positions = [Point2(( \
            loc.x + distance * math.cos(math.pi * 2 * alpha / locationAmount), \
            loc.y + distance * math.sin(math.pi * 2 * alpha / locationAmount))) \
            for alpha in range(locationAmount) # alpha is the angle here, locationAmount is the variable on how accurate the attempts look like a circle (= how many points on a circle)
            for distance in range(minRange, maxRange+1)] # distance depending on minrange and maxrange
        return positions

    def remember_enemy_units(self):
        # Every 60 seconds, clear all remembered units (to clear out killed units)
        #if round(self.get_game_time() % 60) == 0:
        #    self.remembered_enemy_units_by_tag = {}

        # Look through all currently seen units and add them to list of remembered units (override existing)
        for unit in self.known_enemy_units:
            unit.is_known_this_step = True
            self.remembered_enemy_units_by_tag[unit.tag] = unit

        # Convert to an sc2 Units object and place it in self.remembered_enemy_units
        self.remembered_enemy_units = sc2.units.Units([], self._game_data)
        for tag, unit in list(self.remembered_enemy_units_by_tag.items()):
            # Make unit.is_seen = unit.is_visible 
            if unit.is_known_this_step:
                unit.is_seen = unit.is_visible # There are known structures that are not visible
                unit.is_known_this_step = False # Set to false for next step
            else:
                unit.is_seen = False

            # Units that are not visible while we have friendly units nearby likely don't exist anymore, so delete them
            if not unit.is_seen and self.units.closer_than(7, unit).exists:
                del self.remembered_enemy_units_by_tag[tag]
                continue

            self.remembered_enemy_units.append(unit)

    # Remember friendly units' previous state, so we can see if they're taking damage
    def remember_friendly_units(self):
        for unit in self.units:
            unit.is_taking_damage = False

            # If we already remember this friendly unit
            if unit.tag in self.remembered_friendly_units_by_tag:
                health_old = self.remembered_friendly_units_by_tag[unit.tag].health
                shield_old = self.remembered_friendly_units_by_tag[unit.tag].shield

                # Compare its health/shield since last step, to find out if it has taken any damage
                if unit.health < health_old or unit.shield < shield_old:
                    unit.is_taking_damage = True
                
            self.remembered_friendly_units_by_tag[unit.tag] = unit

    def has_order(self, orders, units):
        if type(orders) != list:
            orders = [orders]

        count = 0

        if type(units) == sc2.unit.Unit:
            unit = units
            if len(unit.orders) >= 1 and unit.orders[0].ability.id in orders:
                count += 1
        else:
            for unit in units:
                if len(unit.orders) >= 1 and unit.orders[0].ability.id in orders:
                  count += 1

        return count

    async def order(self, units, order, target=None, silent=True):
        if type(units) != list:
            unit = units
            await self.do(unit(order, target=target))
        else:
            for unit in units:
                await self.do(unit(order, target=target))

# run_game(maps.get("MechDepotLE"), [
#     #Human(Race.Zerg),
#     Bot(Race.Zerg, Overmind()),
#     #Bot(Race.Protoss, CannonLoverBot())
#     Computer(Race.Terran, Difficulty.VeryHard)  
# ], realtime=True)

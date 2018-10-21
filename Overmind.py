from sc2.unit import Unit
from sc2.units import Units
from sc2.data import race_gas, race_worker, race_townhalls, ActionResult, Attribute, Race

import sc2  # pip install sc2
from sc2 import Race, Difficulty, run_game, maps
from sc2.constants import *
from sc2.ids.unit_typeid import *
from sc2.ids.ability_id import *
from sc2.position import Point2, Point3
from sc2.helpers import ControlGroup

from sc2.player import Bot, Computer, Human
import math
import random


class Overmind(sc2.BotAI):
    def __init__(self):
        self.droneUp = True
        self.buildArmy = False
        self.expand = False
        self.buildMore = True
        self.expandTime = 3
        self.combinedActions = []
        self.gases = 0.5
        self.injectInterval = 50
        self.creepTargetDistance = 15  # was 10
        self.creepTargetCountsAsReachedDistance = 10  # was 25
        self.creepSpreadInterval = 10
        self.stopMakingNewTumorsWhenAtCoverage = 0.5  # stops queens from putting down new tumors and save up transfuse energy
        self.attacking = False
        self.defending = False
        self.attackSupply = 190
        self.hqs = [HATCHERY, LAIR, HIVE, COMMANDCENTER, ORBITALCOMMAND, PLANETARYFORTRESS, NEXUS]
        self.ovyScout = False
        self.scouter = None
        self.units_to_ignore = [DRONE, SCV, PROBE, EGG, LARVA, OVERLORD, OVERSEER, OBSERVER, BROODLING, INTERCEPTOR,
                                MEDIVAC, CREEPTUMOR, CREEPTUMORBURROWED, CREEPTUMORQUEEN, CREEPTUMORMISSILE, EGG, QUEEN, DRONEBURROWED, ADEPTPHASESHIFT]
        self.enemies = {}
        self.exactExpansionLocations = []
        self.workersAway = []
        self.lingSpeed = False

    async def on_step(self, iteration):
        self.armyUnits = self.units(ROACH).ready | self.units(ZERGLING).ready | self.units(HYDRALISK).ready | self.units(BROODLORD).ready | self.units(BANELING).ready | self.units(LURKERMP).ready
        self.iteration = iteration
        # print(iteration)
        if iteration == 1:
            await self.chat_send("(glhf)")
            await self.findExactExpansionLocations()
        await self.armyScout()
        await self.lurkerMicro()
        # await self.burrowMicro()
        await self.distribute_workers()
        if iteration % 5 == 0:
            if not self.townhalls.exists:
                await self.chat_send("(gg)")
                await self._client.leave()
            await self.checkExpand()
            await self.checkSupplies()
            await self.makeUpgrades()
            await self.getLair()
            await self.buildStuff()
            await self.morphStuff()
            await self.zergUpgrades()
            await self.getGases()
            await self.buildExtractor()
            await self.buildQueens()
            await self.doQueenInjects(iteration)
            self.assignQueen()
            await self.doCreepSpread()
            await self.zergUpgrades()
            await self.getOverseer()
            await self.moveOverseer()
            await self.makeChangeling()
            await self.moveChangeling()
            # await self.buildBanes()
            await self.defendQueen()
            await self.workerDefence()
            await self.buildLurkers()

            if self.get_game_time() < 600:
                await self.rememberEnemies()
                await self.ovScout()
                await self.checkLingSpeed()

        if iteration % 3 == 0:
            await self.attack()
            await self.defend()
            await self.attackRally()

        await self.do_actions(self.combinedActions)
        self.combinedActions = []
        self.droneUp = True
        self.buildArmy = False
        self.buildMore = True

    ###FUNCTIONS###
    def lurkerGood(self):
        if self.units(LURKERMP).amount >= 10:
            return True
        elif self.units(HYDRALISK).amount < (self.units(LURKERMP).amount + self.units(LURKERMPEGG).amount + self.units(LURKERMPBURROWED).amount) * 2:
            return True
        elif not self.units(LURKERDENMP).exists:
            return True
        else:
            return False

    async def lurkerMicro(self):
        for lurker in self.units(LURKERMP).ready:
            nearby_enemy_units = self.known_enemy_units.closer_than(10, lurker)
            if nearby_enemy_units.amount > 3:
                self.combinedActions.append(lurker(BURROWDOWN_LURKER))

        for lurker in self.units(LURKERMPBURROWED).ready:
            nearby_enemy_units = self.known_enemy_units.closer_than(12, lurker)
            if nearby_enemy_units.amount < 2:
                self.combinedActions.append(lurker(BURROWUP_LURKER))

    async def buildLurkers(self):
        if self.units(LURKERDENMP).exists:
            for hydra in self.units(HYDRALISK).ready:
                if not self.known_enemy_units.closer_than(40, hydra.position):
                    if (self.units(LURKERMP).amount + self.units(LURKERMPEGG).amount + self.units(LURKERMPBURROWED).amount) < 10:
                        # print(self.units(LURKERMP).amount + self.units(LURKERMPEGG).amount)
                        self.combinedActions.append(hydra(MORPH_LURKER))

    async def defendQueen(self):
        enemiesCloseToTh = None
        for th in self.townhalls:
            enemiesCloseToTh = self.known_enemy_units.closer_than(15, th.position)
        if enemiesCloseToTh.amount > 2:
            for unit in self.units(QUEEN).idle:
                self.combinedActions.append(unit.attack(enemiesCloseToTh.random.position))


    async def checkLingSpeed(self):
        if not self.lingSpeed:
            # if self.units(SPAWNINGPOOL).ready.exists:
                # if not await self.has_ability(RESEARCH_ZERGLINGMETABOLICBOOST, self.units(SPAWNINGPOOL).first):
            if self.already_pending_upgrade(UpgradeId.ZERGLINGMOVEMENTSPEED):
                self.lingSpeed = True

    async def workerDefence(self):
        enemiesCloseToTh = None
        for th in self.townhalls.ready:
            enemiesCloseToTh = self.known_enemy_units.filter(lambda unit: not unit.is_flying).closer_than(15, th.position)
        if enemiesCloseToTh:
            if enemiesCloseToTh.amount > 2:
                if self.workers.closer_than(15, enemiesCloseToTh.random.position).amount > enemiesCloseToTh.amount:
                    for worker in self.workers.closer_than(15, enemiesCloseToTh.random.position):
                        target = enemiesCloseToTh.random
                        self.combinedActions.append(worker.attack(target.position))
                        self.workersAway.append(worker)
        for h in self.townhalls:
            for worker in self.workersAway:
                w = self.workers.find_by_tag(worker)
                if w:
                    if w.distance_to(h) > 30:
                        if worker.tag in self.workersAway:
                            self.workersAway.remove(w.tag)
                            self.combinedActions.append(w.move(self.start_location))

    async def armyScout(self):
        if self.iteration % 1800 == 0:
        # if self.get_game_time() % 60 == 0:
            if self.units(ZERGLING).exists:
                roach = self.units(ZERGLING)
                if self.known_enemy_structures.filter(lambda unit: unit.type_id in self.hqs):
                    target = self.known_enemy_structures.filter(lambda unit: unit.type_id in self.hqs).closest_to(
                    self.game_info.map_center).position
                else:
                    target = self.townhalls.random.position
                    self.combinedActions.append(roach.random.attack(target))

    async def morphStuff(self):
        if self.units(LARVA).exists:
            for larva in self.units(LARVA):
                if self.supply_left < 10 and self.already_pending(OVERLORD) < 2 and (self.droneUp or self.buildArmy):
                    if self.can_afford(OVERLORD):
                        self.combinedActions.append(larva.train(OVERLORD))
                elif self.droneUp and self.units(DRONE).amount + self.already_pending(DRONE) < 80 and self.units(DRONE).amount + self.already_pending(DRONE) < 22 * self.townhalls.amount:
                    if self.can_afford(DRONE):
                        self.combinedActions.append(larva.train(DRONE))
                elif self.buildArmy or self.units(DRONE).amount + self.already_pending(DRONE) >= 80 or self.units(DRONE).amount + self.already_pending(DRONE) >= 22 * self.townhalls.amount:
                    # if self.units(SPAWNINGPOOL).exists:
                    #     if self.units(HYDRALISKDEN).exists:
                    #         if(self.units(ZERGLING).amount + self.already_pending(ZERGLING)) + (self.units(BANELING).amount + self.units(BANELINGCOCOON).amount) > (self.units(HYDRALISK).amount + self.already_pending(HYDRALISK)) * 3:
                    #             await self.morphZerg(HYDRALISK)
                    #         else:
                    #             await self.morphZerg(ZERGLING)
                    #     else:
                    #         await self.morphZerg(ZERGLING)
                    # if self.units(GREATERSPIRE).exists:
                    #     if self.units(ZERGLING).amount + self.already_pending(ZERGLING) < 20:
                    #         await self.morphZerg(ZERGLING)
                    #     else:
                    #         await self.morphZerg(CORRUPTOR)
                    if self.vespene < 150 and self.minerals > 1000:
                        if self.can_afford(ZERGLING):
                            self.combinedActions.append(larva.train(ZERGLING))

                    elif self.units(HYDRALISKDEN).exists:
                        if self.lurkerGood() or self.units(HYDRALISK).amount < 5:
                            if self.can_afford(HYDRALISK):
                                self.combinedActions.append(larva.train(HYDRALISK))

                    elif self.units(SPAWNINGPOOL).exists:
                        if self.can_afford(ZERGLING):
                            self.combinedActions.append(larva.train(ZERGLING))

    async def morphZerg(self, unit):
        larva = self.units(LARVA).random
        if self.can_afford(unit):
            self.combinedActions.append(larva.train(unit))

    async def buildStuff(self):
        if self.townhalls.exists:
            if self.buildMore:
                if not self.units(SPAWNINGPOOL).exists:
                    await self.buildZerg(SPAWNINGPOOL)
                # if self.lingSpeed:
                #     if self.units(SPAWNINGPOOL).exists and not self.units(BANELINGNEST).exists:
                #         await self.buildZerg(BANELINGNEST)
                if self.units(LAIR).exists and not self.units(HYDRALISKDEN).exists:
                    if self.vespene > 100:
                        self.droneUp = False
                        self.buildArmy = False
                        await self.buildZerg(HYDRALISKDEN)
                if self.units(EVOLUTIONCHAMBER).amount + self.already_pending(EVOLUTIONCHAMBER) < 2 and self.townhalls.amount > self.units(EVOLUTIONCHAMBER).amount + self.already_pending(EVOLUTIONCHAMBER) * 0.4 and self.lingSpeed:
                    await self.buildZerg(EVOLUTIONCHAMBER)
                if self.units(HYDRALISKDEN).exists and not self.units(LURKERDENMP).exists:
                    await self.buildZerg(LURKERDENMP)

    async def buildZerg(self, building):
        if self.townhalls.exists:
            hq = self.townhalls.random
            if self.can_afford(building):
                if not self.already_pending(building):
                    await self.build(building, near=hq.position.towards(self.game_info.map_center, 8))

    async def makeUpgrades(self):
        if self.buildMore:
            if self.units(SPAWNINGPOOL).ready.exists:
                if await self.has_ability(RESEARCH_ZERGLINGMETABOLICBOOST, self.units(SPAWNINGPOOL).first):
                    if self.vespene > 100:
                        self.droneUp = False
                        self.buildArmy = False
                        await self.doUpgrades(RESEARCH_ZERGLINGMETABOLICBOOST, SPAWNINGPOOL)
            if self.lingSpeed:
                if self.units(HYDRALISKDEN).exists:
                    if await self.has_ability(RESEARCH_GROOVEDSPINES, self.units(HYDRALISKDEN).first):
                        await self.doUpgrades(RESEARCH_GROOVEDSPINES, HYDRALISKDEN)
                if self.units(HYDRALISKDEN).exists:
                    if await self.has_ability(RESEARCH_MUSCULARAUGMENTS, self.units(HYDRALISKDEN).first):
                        await self.doUpgrades(RESEARCH_MUSCULARAUGMENTS, HYDRALISKDEN)
                # if self.units(HATCHERY).exists:
                #     if await self.has_ability(RESEARCH_BURROW, self.units(HATCHERY).first):
                #         await self.doUpgrades(RESEARCH_BURROW, HATCHERY)
                # if self.units(BANELINGNEST).exists:
                #     if await self.has_ability(RESEARCH_CENTRIFUGALHOOKS, self.units(BANELINGNEST).first):
                #         await self.doUpgrades(RESEARCH_CENTRIFUGALHOOKS, BANELINGNEST)

    async def buildBanes(self):
        if self.units(HYDRALISKDEN).exists:
            for ling in self.units(ZERGLING).ready:
                if not self.known_enemy_units.closer_than(65, ling.position):
                    if self.units(BANELINGNEST).exists:
                        if self.units(BANELING).amount + self.units(BANELINGCOCOON).amount <= self.units(ZERGLING).amount:
                            self.combinedActions.append(ling(MORPHZERGLINGTOBANELING_BANELING))


    async def doUpgrades(self, upgrade, building):
        if self.units(building).exists:
            b = self.units(building).first
            if b.noqueue:
                if await self.has_ability(upgrade, b):
                    if self.can_afford(upgrade):
                        self.combinedActions.append(b(upgrade))
    # async def roachSpeed(self):
    #     if self.buildMore:
    #         if self.units(ROACHWARREN).exists:
    #             rw = self.units(ROACHWARREN).first
    #             if rw.noqueue:
    #                 if (self.units(LAIR).exists or self.units(HIVE).exists) and not self.already_pending(LAIR):
    #                     if await self.has_ability(RESEARCH_GLIALREGENERATION, rw):
    #                         if self.can_afford(RESEARCH_GLIALREGENERATION):
    #                             self.combinedActions.append(rw(RESEARCH_GLIALREGENERATION))

    async def checkExpand(self):
        enemiesNearby = 0
        if self.get_game_time() / 60 > 9:
            self.expandTime = 3.5
        expand_every = self.expandTime * 60
        prefered_base_count = 2 + int(math.floor(self.get_game_time() / expand_every))
        current_base_count = self.townhalls.amount
        if self.buildArmy:
            prefered_base_count = 0

        if self.minerals > 900:
            prefered_base_count += 1

        for th in self.townhalls:
            enemiesNearby = self.known_enemy_units.not_structure.filter(lambda unit: unit.type_id not in self.units_to_ignore).closer_than(30, th)

        if prefered_base_count > current_base_count and current_base_count < 9 and not self.already_pending(HATCHERY) and enemiesNearby.amount < 2:
            self.expand = True
            self.droneUp = False
            self.buildMore = False

        if not self.already_pending(HATCHERY) and enemiesNearby.amount < 2:
            if self.expand:
                if self.minerals >= 300:
                    location = await self.get_next_expansion()
                    await self.build(HATCHERY, near=location, max_distance=10, random_alternative=False,
                                     placement_step=1)

        if prefered_base_count <= current_base_count:
            self.expand = False


    async def buildExtractor(self):
        if not self.already_pending(EXTRACTOR):
            if self.get_game_time() > 60:
                if self.townhalls.exists:
                    hq = self.townhalls.random
                    if self.buildMore:
                        vaspenes = self.state.vespene_geyser.closer_than(15.0, hq)
                        if (self.units(EXTRACTOR).amount / (self.townhalls.amount * self.gases)) < 1:
                            for vaspene in vaspenes:
                                if not self.can_afford(EXTRACTOR):
                                    break
                                worker = self.select_build_worker(vaspene.position)
                                if worker is None:
                                    break
                                if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                                        self.combinedActions.append(worker.build(EXTRACTOR, vaspene))

    async def getGases(self):
        if self.get_game_time() > 180:
            if self.minerals > 0 and self.vespene > 0:
                if (self.minerals / self.vespene) >= 3 and self.gases <= 2:
                    self.gases += 0.25
                elif (self.vespene / self.minerals) >= 3 and self.gases >= 0.5:
                    self.gases += -0.25

    async def getLair(self):
        if self.units(SPAWNINGPOOL).ready.exists:
            if self.units(HATCHERY).idle.exists:
                hq = self.units(HATCHERY).idle.random
                if not await self.hasLair() and self.vespene >= 100:
                    if not (self.units(HIVE).exists or self.units(LAIR).exists):
                        self.droneUp = False
                        self.buildArmy = False
                        self.buildMore = False
                        if self.can_afford(LAIR):
                            self.combinedActions.append(hq.build(LAIR))

    async def buildQueens(self):
        if self.buildMore:
            if self.townhalls.exists:
                for hq in self.townhalls.noqueue.ready:
                    if self.units(SPAWNINGPOOL).ready.exists:
                        if self.units(QUEEN).amount < (self.townhalls.amount * 1.2):
                            if self.can_afford(QUEEN) and self.units(QUEEN).amount < 10:
                                self.combinedActions.append(hq.train(QUEEN))

    def assignQueen(self):
        maxAmountInjectQueens = self.townhalls.amount
        # # list of all alive queens and bases, will be used for injecting
        if not hasattr(self, "queensAssignedHatcheries"):
            self.queensAssignedHatcheries = {}

        if maxAmountInjectQueens == 0:
            self.queensAssignedHatcheries = {}

        queensNoInjectPartner = self.units(QUEEN).filter(
            lambda q: q.tag not in self.queensAssignedHatcheries.keys())
        basesNoInjectPartner = self.townhalls.filter(
            lambda h: h.tag not in self.queensAssignedHatcheries.values() and h.build_progress > 0.8)

        for queen in queensNoInjectPartner:
            if basesNoInjectPartner.amount == 0:
                break
            closestBase = basesNoInjectPartner.closest_to(queen)
            self.queensAssignedHatcheries[queen.tag] = closestBase.tag
            basesNoInjectPartner = basesNoInjectPartner - [closestBase]
            break  # else one hatch gets assigned twice

    async def doQueenInjects(self, iteration):
        # list of all alive queens and bases, will be used for injecting
        aliveQueenTags = [queen.tag for queen in self.units(QUEEN)]  # list of numbers (tags / unit IDs)
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
                    if queen.energy >= 25 and queen.is_idle and not hatch.has_buff(QUEENSPAWNLARVATIMER):
                        self.combinedActions.append(queen(EFFECT_INJECTLARVA, hatch))
                else:
                    if iteration % self.injectInterval == 0 and queen.is_idle and queen.position.distance_to(
                            hatch.position) > 10:
                        self.combinedActions.append(queen(AbilityId.MOVE, hatch.position.to2))

            # clear queen tags (in case queen died or hatch got destroyed) from the dictionary outside the iteration loop
            for tag in toRemoveTags:
                self.queensAssignedHatcheries.pop(tag)


    async def attackRally(self):
        if not self.attacking and not self.defending:
            attack_location = self.get_rally_location()
            for unit in self.armyUnits.idle:
                if unit.distance_to(attack_location) > 8:
                    self.combinedActions.append(unit.attack(attack_location))

    async def attack(self):
        if not self.defending:
            if self.supply_used < self.attackSupply - 20:
                self.attacking = False
            if self.supply_used > self.attackSupply and self.attacking:
                self.attacking = True
                for unit in self.armyUnits.idle:
                    self.combinedActions.append(unit.attack(self.find_target(self.state).position))
            elif self.supply_used > self.attackSupply:
                self.attacking = True
                for unit in self.armyUnits:
                    self.combinedActions.append(unit.attack(self.find_target(self.state).position))

    async def updateCreepCoverage(self, stepSize=None):
        if stepSize is None:
            stepSize = self.creepTargetDistance
        ability = self._game_data.abilities[ZERGBUILD_CREEPTUMOR.value]

        positions = [Point2((x, y)) \
                     for x in range(self._game_info.playable_area[0] + stepSize,
                                    self._game_info.playable_area[0] + self._game_info.playable_area[2] - stepSize,
                                    stepSize) \
                     for y in range(self._game_info.playable_area[1] + stepSize,
                                    self._game_info.playable_area[1] + self._game_info.playable_area[3] - stepSize,
                                    stepSize)]

        validPlacements = await self._client.query_building_placement(ability, positions)
        successResults = [
            ActionResult.Success,  # tumor can be placed there, so there must be creep
            ActionResult.CantBuildLocationInvalid,  # location is used up by another building or doodad,
            ActionResult.CantBuildTooFarFromCreepSource,  # - just outside of range of creep
            # ActionResult.CantSeeBuildLocation - no vision here
        ]
        # self.positionsWithCreep = [p for index, p in enumerate(positions) if validPlacements[index] in successResults]
        self.positionsWithCreep = [p for valid, p in zip(validPlacements, positions) if valid in successResults]
        self.positionsWithoutCreep = [p for index, p in enumerate(positions) if
                                      validPlacements[index] not in successResults]
        self.positionsWithoutCreep = [p for valid, p in zip(validPlacements, positions) if valid not in successResults]
        return self.positionsWithCreep, self.positionsWithoutCreep

    async def doCreepSpread(self):
        # only use queens that are not assigned to do larva injects
        allTumors = self.units(CREEPTUMOR) | self.units(CREEPTUMORBURROWED) | self.units(CREEPTUMORQUEEN)

        if not hasattr(self, "usedCreepTumors"):
            self.usedCreepTumors = set()

        # gather all queens that are not assigned for injecting and have 25+ energy
        if hasattr(self, "queensAssignedHatcheries"):
            unassignedQueens = self.units(QUEEN).filter(
                lambda q: (q.tag not in self.queensAssignedHatcheries and q.energy >= 25 or q.energy >= 50) and (
                            q.is_idle or len(q.orders) == 1 and q.orders[0].ability.id in [AbilityId.MOVE]))
        else:
            unassignedQueens = self.units(QUEEN).filter(lambda q: q.energy >= 25 and (
                        q.is_idle or len(q.orders) == 1 and q.orders[0].ability.id in [AbilityId.MOVE]))

        # update creep coverage data and points where creep still needs to go
        if not hasattr(self, "positionsWithCreep") or self.iteration % self.creepSpreadInterval * 10 == 0:
            posWithCreep, posWithoutCreep = await self.updateCreepCoverage()
            totalPositions = len(posWithCreep) + len(posWithoutCreep)
            self.creepCoverage = len(posWithCreep) / totalPositions
            # print(self.getTimeInSeconds(), "creep coverage:", creepCoverage)

        # filter out points that have already tumors / bases near them
        if hasattr(self, "positionsWithoutCreep"):
            self.positionsWithoutCreep = [x for x in self.positionsWithoutCreep if
                                          (allTumors | self.townhalls).closer_than(
                                              self.creepTargetCountsAsReachedDistance, x).amount < 1 or (
                                                      allTumors | self.townhalls).closer_than(
                                              self.creepTargetCountsAsReachedDistance + 10,
                                              x).amount < 5]  # have to set this to some values or creep tumors will clump up in corners trying to get to a point they cant reach

        # make all available queens spread creep until creep coverage is reached 50%
        if hasattr(self, "creepCoverage") and (
                self.creepCoverage < self.stopMakingNewTumorsWhenAtCoverage or allTumors.amount - len(
                self.usedCreepTumors) < 25):
            for queen in unassignedQueens:
                # locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=queen, minRange=3, maxRange=30, stepSize=2, locationAmount=16)
                if self.townhalls.ready.exists:
                    locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=queen,
                                                                  minRange=3, maxRange=30, stepSize=2,
                                                                  locationAmount=16)
                    # locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=self.townhalls.ready.random, minRange=3, maxRange=30, stepSize=2, locationAmount=16)
                    if locations is not None:
                        for loc in locations:
                            err = self.combinedActions.append(queen(BUILD_CREEPTUMOR_QUEEN, loc))
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
                locations = await self.findCreepPlantLocation(self.positionsWithoutCreep, castingUnit=tumor,
                                                              minRange=10,
                                                              maxRange=10)  # min range could be 9 and maxrange could be 11, but set both to 10 and performance is a little better
                if locations is not None:
                    for loc in locations:
                        err = self.combinedActions.append(tumor(BUILD_CREEPTUMOR_TUMOR, loc))
                        if not err:
                            tumorsMadeTumorPositions.add((tumor.position.x, tumor.position.y))
                            self.usedCreepTumors.add(tumor.tag)
                            break

    async def findCreepPlantLocation(self, targetPositions, castingUnit, minRange=None, maxRange=None, stepSize=1,
                                     onlyAttemptPositionsAroundUnit=False, locationAmount=32,
                                     dontPlaceTumorsOnExpansions=True):
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
        positions = self.getPositionsAroundUnit(castingUnit, minRange=minRange, maxRange=maxRange,
                                                stepSize=stepSize,
                                                locationAmount=locationAmount)

        # stop when map is full with creep
        if len(self.positionsWithoutCreep) == 0:
            return None

        # filter positions that would block expansions
        if dontPlaceTumorsOnExpansions and hasattr(self, "exactExpansionLocations"):
            positions = [x for x in positions if
                         self.getHighestDistance(x.closest(self.exactExpansionLocations), x) > 3]
            # TODO: need to check if this doesnt have to be 6 actually
            # this number cant also be too big or else creep tumors wont be placed near mineral fields where they can actually be placed

        # check if any of the positions are valid
        validPlacements = await self._client.query_building_placement(ability, positions)

        # filter valid results
        validPlacements = [p for index, p in enumerate(positions) if validPlacements[index] == ActionResult.Success]

        allTumors = self.units(CREEPTUMOR) | self.units(CREEPTUMORBURROWED) | self.units(CREEPTUMORQUEEN)
        # usedTumors = allTumors.filter(lambda x:x.tag in self.usedCreepTumors)
        unusedTumors = allTumors.filter(lambda x: x.tag not in self.usedCreepTumors)
        if castingUnit is not None and castingUnit in allTumors:
            unusedTumors = unusedTumors.filter(lambda x: x.tag != castingUnit.tag)

        # filter placements that are close to other unused tumors
        if len(unusedTumors) > 0:
            validPlacements = [x for x in validPlacements if x.distance_to(unusedTumors.closest_to(x)) >= 10]

        validPlacements.sort(key=lambda x: x.distance_to(x.closest(self.positionsWithoutCreep)), reverse=False)

        if len(validPlacements) > 0:
            return validPlacements
        return None

    async def zergUpgrades(self):
        if self.buildMore:
            if self.lingSpeed:
                if self.units(EVOLUTIONCHAMBER).exists:
                    for evochamber in self.units(EVOLUTIONCHAMBER).ready:
                        if evochamber.noqueue:
                            for upgrade_level in range(1, 4):
                                upgrade_armor_id = getattr(sc2.constants,
                                                           "RESEARCH_ZERGGROUNDARMORLEVEL" + str(upgrade_level))
                                upgrade_missle_id = getattr(sc2.constants,
                                                            "RESEARCH_ZERGMISSILEWEAPONSLEVEL" + str(upgrade_level))
                                upgrade_melee_id = getattr(sc2.constants,
                                                           "RESEARCH_ZERGMELEEWEAPONSLEVEL" + str(upgrade_level))
                                if await self.has_ability(upgrade_missle_id, evochamber):
                                    if self.can_afford(upgrade_missle_id):
                                        self.combinedActions.append(evochamber(upgrade_missle_id))
                                elif await self.has_ability(upgrade_armor_id, evochamber):
                                    if self.can_afford(upgrade_armor_id):
                                        self.combinedActions.append(evochamber(upgrade_armor_id))
                                elif await self.has_ability(upgrade_melee_id, evochamber):
                                    if self.can_afford(upgrade_melee_id):
                                        await self.do(evochamber(upgrade_melee_id))

    async def defend(self):
        enemiesCloseToTh = None
        for th in self.townhalls:
            if self.get_game_time() < 900:
                enemiesCloseToTh = self.known_enemy_units.closer_than(30, th.position)
            else:
                enemiesCloseToTh = self.known_enemy_units.closer_than(15, th.position)
        if enemiesCloseToTh and not self.attacking:
            self.defending = True
            for unit in self.armyUnits.idle:
                self.combinedActions.append(unit.attack(enemiesCloseToTh.random.position))
        elif not enemiesCloseToTh:
            self.defending = False

    async def getOverseer(self):
        if (self.units(LAIR) | self.units(HIVE)).exists and (
                self.units(OVERSEER) | self.units(OVERLORDCOCOON)).amount < 2:
            if self.units(OVERLORD).exists and self.can_afford(OVERSEER):
                ov = self.units(OVERLORD).random
                self.combinedActions.append(ov(MORPH_OVERSEER))

    async def burrowMicro(self):
        for unit in self.units(ROACH).ready:
            nearby_enemy_units = self.known_enemy_units.closer_than(10, unit)
            if unit.health / unit.health_max < 3 / 10 and nearby_enemy_units.amount > 2:
                abilities = await self.get_available_abilities(unit)
                if AbilityId.BURROWDOWN_ROACH in abilities and self.can_afford(BURROWDOWN_ROACH):
                    self.combinedActions.append(unit(BURROWDOWN_ROACH))

        for unit in self.units(ROACHBURROWED).ready:
            nearby_enemy_units = self.known_enemy_units.closer_than(10, unit)
            if (unit.health / unit.health_max > 6 / 10 or nearby_enemy_units.amount < 2) and unit.is_burrowed:
                abilities = await self.get_available_abilities(unit)
                if AbilityId.BURROWUP_ROACH in abilities and self.can_afford(BURROWUP_ROACH):
                    self.combinedActions.append(unit(BURROWUP_ROACH))

        for unit in self.units(HYDRALISK).ready:
            nearby_enemy_units = self.known_enemy_units.closer_than(10, unit)
            if unit.health / unit.health_max < 3 / 10 and nearby_enemy_units.amount > 2:
                abilities = await self.get_available_abilities(unit)
                if AbilityId.BURROWDOWN_HYDRALISK in abilities and self.can_afford(BURROWDOWN_HYDRALISK):
                    self.combinedActions.append(unit(BURROWDOWN_HYDRALISK))

        for unit in self.units(HYDRALISKBURROWED).ready:
            nearby_enemy_units = self.known_enemy_units.closer_than(10, unit)
            if (unit.health / unit.health_max > 6 / 10 or nearby_enemy_units.amount < 2) and unit.is_burrowed:
                abilities = await self.get_available_abilities(unit)
                if AbilityId.BURROWUP_HYDRALISK in abilities and self.can_afford(BURROWUP_HYDRALISK):
                    self.combinedActions.append(unit(BURROWUP_HYDRALISK))

    async def moveOverseer(self):
        if self.armyUnits.exists:
            lowest_health = self.armyUnits.random
            for unit in self.armyUnits:
                if unit.health < lowest_health.health:
                    lowest_health = unit
                for medic in self.units(OVERSEER).ready:
                    self.combinedActions.append(medic.attack(lowest_health.position))

    async def makeChangeling(self):
        for overseer in self.units(OVERSEER).ready:
            if overseer.energy >= 50:
                self.combinedActions.append(overseer(SPAWNCHANGELING_SPAWNCHANGELING))

    async def moveChangeling(self):
        for unit in self.units(CHANGELING).ready.idle:
            if self.known_enemy_structures.filter(lambda unit: unit.type_id in self.hqs):
                target = self.known_enemy_structures.filter(lambda unit: unit.type_id in self.hqs).closest_to(
                    self.game_info.map_center).position
            else:
                target = random.choice(list(self.expansion_locations.keys()))
            self.combinedActions.append(unit.attack(target))
        changeling = self.units(CHANGELINGZEALOT).ready | self.units(CHANGELINGMARINESHIELD).ready | self.units(CHANGELINGMARINE).ready | self.units(CHANGELINGZERGLINGWINGS).ready | self.units(CHANGELINGZERGLING).ready
        for change in changeling:
            self.combinedActions.append(change.attack(self.find_target(self.state).position))

    async def ovScout(self):
        if not self.ovyScout:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            self.combinedActions.append(ov.move(self.enemy_start_locations[0].position))
            self.ovyScout = True

    async def scout(self):
        if self.workers.exists:
            if self.units.find_by_tag(self.scouter) == None:
                worker = self.workers.random
                self.scouter = worker.tag
                scout = self.workers.find_by_tag(self.scouter)
                if self.get_game_time() < 120:
                    random_exp_location = random.choice(self.enemy_start_locations)
                else:
                    random_exp_location = random.choice(list(self.expansion_locations.keys()))
                    self.combinedActions.append(scout.move(random_exp_location))

            scout = self.workers.find_by_tag(self.scouter)
            if self.get_game_time() < 180:
                random_exp_location = random.choice(self.enemy_start_locations)
            else:
                random_exp_location = random.choice(list(self.expansion_locations.keys()))

            if scout.is_idle:
                self.combinedActions.append(scout.move(random_exp_location))

            # Basic avoidance: If enemy is too close, go to map center
            nearby_enemy_units = self.known_enemy_units.not_structure.filter(
                lambda unit: unit.type_id not in self.units_to_ignore).closer_than(5, scout)
            if nearby_enemy_units.exists:
                new_random_exp_location = random.choice(list(self.expansion_locations.keys()))

                random_exp_location = new_random_exp_location
                self.combinedActions.append(scout.move(random_exp_location))

            # We're close enough, so change target
            if scout.distance_to(random_exp_location) < 1:
                random_exp_location = random.choice(list(self.expansion_locations.keys()))
                self.combinedActions.append(scout.move(random_exp_location))

    async def rememberEnemies(self):
        for unit in self.known_enemy_units.not_structure.filter(lambda unit: unit.type_id not in self.units_to_ignore):
            if not unit.tag in self.enemies:
                enemySupply = 0
                enemySupply += unit._type_data._proto.food_required
                self.enemies[unit.tag] = enemySupply
                # print(unit.type_id)
                # print(unit._type_data._proto.food_required)



    async def on_unit_destroyed(self, unit_tag):
        if unit_tag in self.enemies:
            del self.enemies[unit_tag]


    async def checkSupplies(self):
        if self.get_game_time() < 400:
            checkAmount = 1.2
            mySupply = 0
            enemySupply = 0
            for unit in self.armyUnits:
                mySupply += unit._type_data._proto.food_required

            for tags, supply in self.enemies.items():
                enemySupply += supply
            # print("Theirs: " + str(enemySupply))
            # print("Mine: " + str(mySupply * checkAmount))
            if self.get_game_time() > 300:
                checkAmount = 1.5
            elif self.get_game_time() > 200:
                checkAmount = 1.35

            if enemySupply > mySupply * checkAmount:
                self.buildArmy = True
                self.droneUp = False



    ######USE FUNCTIONS######
    def getHighestDistance(self, unit1, unit2):
        # returns just the highest distance difference, return max(abs(x2-x1), abs(y2-y1))
        # required for creep tumor placement
        assert isinstance(unit1, (Unit, Point2, Point3))
        assert isinstance(unit2, (Unit, Point2, Point3))
        if isinstance(unit1, Unit):
            unit1 = unit1.position.to2
        if isinstance(unit2, Unit):
            unit2 = unit2.position.to2
        return max(abs(unit1.x - unit2.x), abs(unit1.y - unit2.y))

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

    async def has_ability(self, ability, unit):
        abilities = await self.get_available_abilities(unit)
        if ability in abilities:
            return True
        else:
            return False

    def find_target(self, state):
        if len(self.known_enemy_units) > 0:
            return random.choice(self.known_enemy_units)
        elif len(self.known_enemy_structures) > 0:
            return random.choice(self.known_enemy_structures)
        else:
            return self.enemy_start_locations[0]

    def get_rally_location(self):
        if self.townhalls.exists:
            hq = self.townhalls.closest_to(self.game_info.map_center).position
            rally_location = hq.position.towards(self.game_info.map_center, 6)
            return rally_location
        else:
            rally_location = self.start_location
            return rally_location

    async def hasLair(self):
        if (self.units(LAIR).amount > 0):
            return True
        morphingYet = False
        for h in self.units(HATCHERY):
            if CANCEL_MORPHLAIR in await self.get_available_abilities(h):
                morphingYet = True
                break
        if morphingYet:
            return True
        return False

    def get_game_time(self):
        return self.state.game_loop * 0.725 * (1 / 16)

    async def expandNow(self, townhall, building=None, max_distance=10, location=None):
        """Takes new expansion."""

        # if not building:
        #     building = self.townhalls.first.type_id
        #
        # assert isinstance(building, UnitTypeId)

        if not location:
            location = await self.get_next_expansion()

        if self.minerals >= 300:
            await self.build(townhall, near=location, max_distance=max_distance, random_alternative=False, placement_step=1)

    async def distribute_workers(self, performanceHeavy=True, onlySaturateGas=False):
        # expansion_locations = self.expansion_locations
        # owned_expansions = self.owned_expansions
        if self.townhalls.exists:
            for w in self.workers.idle:
                th = self.townhalls.closest_to(w)
                mfs = self.state.mineral_field.closer_than(10, th)
                if mfs:
                    mf = mfs.closest_to(w)
                    if mf.tag != self.scouter:
                        self.combinedActions.append(w.gather(mf))

        mineralTags = [x.tag for x in self.state.units.mineral_field]
        # gasTags = [x.tag for x in self.state.units.vespene_geyser]
        geyserTags = [x.tag for x in self.geysers]

        workerPool = self.units & []
        workerPoolTags = set()

        # find all geysers that have surplus or deficit
        deficitGeysers = {}
        surplusGeysers = {}
        for g in self.geysers.filter(lambda x: x.vespene_contents > 0):
            # only loop over geysers that have still gas in them
            deficit = g.ideal_harvesters - g.assigned_harvesters
            if deficit > 0:
                deficitGeysers[g.tag] = {"unit": g, "deficit": deficit}
            elif deficit < 0:
                surplusWorkers = self.workers.closer_than(10, g).filter(
                    lambda w: w not in workerPoolTags and len(w.orders) == 1 and w.orders[0].ability.id in [
                        AbilityId.HARVEST_GATHER] and w.orders[0].target in geyserTags)
                # workerPool.extend(surplusWorkers)
                for i in range(-deficit):
                    if surplusWorkers.amount > 0:
                        w = surplusWorkers.pop()
                        workerPool.append(w)
                        workerPoolTags.add(w.tag)
                surplusGeysers[g.tag] = {"unit": g, "deficit": deficit}

        # find all townhalls that have surplus or deficit
        deficitTownhalls = {}
        surplusTownhalls = {}
        if not onlySaturateGas:
            for th in self.townhalls:
                deficit = th.ideal_harvesters - th.assigned_harvesters
                if deficit > 0:
                    deficitTownhalls[th.tag] = {"unit": th, "deficit": deficit}
                elif deficit < 0:
                    surplusWorkers = self.workers.closer_than(10, th).filter(
                        lambda w: w.tag not in workerPoolTags and len(w.orders) == 1 and w.orders[0].ability.id in [
                            AbilityId.HARVEST_GATHER] and w.orders[0].target in mineralTags)
                    # workerPool.extend(surplusWorkers)
                    for i in range(-deficit):
                        if surplusWorkers.amount > 0:
                            w = surplusWorkers.pop()
                            workerPool.append(w)
                            workerPoolTags.add(w.tag)
                    surplusTownhalls[th.tag] = {"unit": th, "deficit": deficit}

            if all([len(deficitGeysers) == 0, len(surplusGeysers) == 0,
                    len(surplusTownhalls) == 0 or deficitTownhalls == 0]):
                # cancel early if there is nothing to balance
                return

        # check if deficit in gas less or equal than what we have in surplus, else grab some more workers from surplus bases
        deficitGasCount = sum(
            gasInfo["deficit"] for gasTag, gasInfo in deficitGeysers.items() if gasInfo["deficit"] > 0)
        surplusCount = sum(-gasInfo["deficit"] for gasTag, gasInfo in surplusGeysers.items() if gasInfo["deficit"] < 0)
        surplusCount += sum(-thInfo["deficit"] for thTag, thInfo in surplusTownhalls.items() if thInfo["deficit"] < 0)

        if deficitGasCount - surplusCount > 0:
            # grab workers near the gas who are mining minerals
            for gTag, gInfo in deficitGeysers.items():
                if workerPool.amount >= deficitGasCount:
                    break
                workersNearGas = self.workers.closer_than(10, gInfo["unit"]).filter(
                    lambda w: w.tag not in workerPoolTags and len(w.orders) == 1 and w.orders[0].ability.id in [
                        AbilityId.HARVEST_GATHER] and w.orders[0].target in mineralTags)
                while workersNearGas.amount > 0 and workerPool.amount < deficitGasCount:
                    w = workersNearGas.pop()
                    workerPool.append(w)
                    workerPoolTags.add(w.tag)

        # now we should have enough workers in the pool to saturate all gases, and if there are workers left over, make them mine at townhalls that have mineral workers deficit
        for gTag, gInfo in deficitGeysers.items():
            if performanceHeavy:
                # sort furthest away to closest (as the pop() function will take the last element)
                workerPool.sort(key=lambda x: x.distance_to(gInfo["unit"]), reverse=True)
            for i in range(gInfo["deficit"]):
                if workerPool.amount > 0:
                    w = workerPool.pop()
                    if w.tag != self.scouter:
                        if len(w.orders) == 1 and w.orders[0].ability.id in [AbilityId.HARVEST_RETURN]:
                            self.combinedActions.append(w.gather(gInfo["unit"], queue=True))
                        else:
                            self.combinedActions.append(w.gather(gInfo["unit"]))

        if not onlySaturateGas:
            # if we now have left over workers, make them mine at bases with deficit in mineral workers
            for thTag, thInfo in deficitTownhalls.items():
                if performanceHeavy:
                    # sort furthest away to closest (as the pop() function will take the last element)
                    workerPool.sort(key=lambda x: x.distance_to(thInfo["unit"]), reverse=True)
                for i in range(thInfo["deficit"]):
                    if workerPool.amount > 0:
                        w = workerPool.pop()
                        if w:
                            if w.tag != self.scouter:
                                mf = self.state.mineral_field.closer_than(10, thInfo["unit"]).closest_to(w)
                                if len(w.orders) == 1 and w.orders[0].ability.id in [AbilityId.HARVEST_RETURN]:
                                    self.combinedActions.append(w.gather(mf, queue=True))
                                else:
                                    self.combinedActions.append(w.gather(mf))

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
            for alpha in range(locationAmount)
            # alpha is the angle here, locationAmount is the variable on how accurate the attempts look like a circle (= how many points on a circle)
            for distance in range(minRange, maxRange + 1)]  # distance depending on minrange and maxrange
        return positions

    async def findExactExpansionLocations(self):
        # execute this on start, finds all expansions where creep tumors should not be build near
        self.exactExpansionLocations = []
        for loc in self.expansion_locations.keys():
            self.exactExpansionLocations.append(await self.find_placement(HATCHERY, loc, minDistanceToResources=5.5, placement_step=1))  # TODO: change mindistancetoresource so that a hatch still has room to be built

# run_game(maps.get("AbyssalReefLE"), [
#     # Human(Race.Zerg),
#     Bot(Race.Zerg, Overmind()),
#     #Bot(Race.Protoss, CannonLoverBot())
#     # Computer(Race.Random, Difficulty.VeryHard)
#     Bot(Race.Random, Trinity()),
# ], realtime=False)



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
from sc2.score import ScoreDetails

from sc2.player import Bot, Computer, Human
import math
import random


class Overmind(sc2.BotAI):
    def __init__(self):
        self.combinedActions = []
        self.unit_memory = {}
        self.structure_memory = {}
        self.units_to_ignore = [DRONE, SCV, PROBE, EGG, LARVA, OVERLORD, OVERSEER, OBSERVER, BROODLING, INTERCEPTOR,
                                MEDIVAC, CREEPTUMOR, CREEPTUMORBURROWED, CREEPTUMORQUEEN, CREEPTUMORMISSILE, EGG, QUEEN,
                                DRONEBURROWED, ADEPTPHASESHIFT]
        self.want = "drone"
        self.workers_away = []
        self.game_time = 0
        self.ling_speed = False
        self.melee_upgrades = 0
        self.armor_upgrades = 0
        self.crack_ling = False
        self.bane_speed = False
        self.expand_time = 3
        self.stop_droning = False
        self.overlord_scout_level = 0
        self.injectInterval = 50
        self.creepTargetDistance = 15  # was 10
        self.creepTargetCountsAsReachedDistance = 10  # was 25
        self.creepSpreadInterval = 10
        self.stopMakingNewTumorsWhenAtCoverage = 0.5  # stops queens from putting down new tumors and save up transfuse energy

    async def on_step(self, iteration):
        self.game_time = self.get_game_time() / 60
        self.ground_enemies = self.known_enemy_units.not_flying.not_structure
        await self.do_actions(self.combinedActions)
        self.combinedActions = []
        self.iteration = iteration
        if not iteration:
            self.split_workers()
        await self.overlord_scout()
        self.set_game_step()
        await self.remember_units()
        await self.train_units()
        await self.distribute_workers()
        await self.defence()
        await self.macro_decisions()
        await self.build_extractor()
        await self.check_expand()
        await self.doQueenInjects(iteration)
        self.assignQueen()
        await self.doCreepSpread()


    ###FUNCTIONS##
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
        if not hasattr(self, "positionsWithCreep") or self.iteration % self.creepSpreadInterval == 0:
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

    async def overlord_scout(self):
        if self.game_time > 0 and self.overlord_scout_level == 0:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.overlord_scout_level = 1
        if self.game_time > 1 and self.overlord_scout_level == 1:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.overlord_scout_level = 2
        if self.game_time > 2 and self.overlord_scout_level == 2:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.overlord_scout_level = 3
        if self.game_time > 4 and self.overlord_scout_level == 3:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.overlord_scout_level = 4
        if self.game_time > 6 and self.overlord_scout_level == 4:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.overlord_scout_level = 5
        if self.game_time > 8 and self.overlord_scout_level == 5:
            ov = self.units(OVERLORD).closest_to(self.enemy_start_locations[0])
            await self.do(ov.move(self.enemy_start_locations[0].position))
            self.overlord_scout_level = 6

    async def check_expand(self):
        enemiesNearby = 0
        if self.get_game_time() / 60 > 9:
            self.expand_time = 3.5
        expand_every = self.expand_time * 60
        prefered_base_count = 2 + int(math.floor(self.get_game_time() / expand_every))
        current_base_count = self.townhalls.amount

        if self.minerals > 900:
            prefered_base_count += 1

        location = await self.get_next_expansion()
        enemiesNearby = self.known_enemy_units.filter(
            lambda unit: unit.type_id not in self.units_to_ignore).closer_than(45, location)

        if prefered_base_count > current_base_count and current_base_count < 9 and not self.already_pending(
                HATCHERY) and enemiesNearby.amount < 2:
            if self.minerals >= 300:
                location = await self.get_next_expansion()
                await self.build(HATCHERY, near=location, max_distance=10, random_alternative=False,
                                 placement_step=1)

    async def build_extractor(self):
        if not self.already_pending(EXTRACTOR):
            if self.game_time > 1:
                if self.townhalls.exists:
                    hq = self.townhalls.random
                    vaspenes = self.state.vespene_geyser.closer_than(15.0, hq)
                    if self.townhalls.amount < 4:
                        if (self.units(EXTRACTOR).amount / self.townhalls.amount) < 1:
                            vaspene = vaspenes.random
                            if self.can_afford(EXTRACTOR):
                                worker = self.select_build_worker(vaspene.position)
                                if worker:
                                    if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                                        if not self.already_pending(EXTRACTOR):
                                            self.combinedActions.append(worker.build(EXTRACTOR, vaspene))
                    if self.townhalls.amount >= 4:
                        if (self.units(EXTRACTOR).amount / self.townhalls.amount) < 1.5:
                            vaspene = vaspenes.random
                            if self.can_afford(EXTRACTOR):
                                worker = self.select_build_worker(vaspene.position)
                                if worker:
                                    if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                                        if not self.already_pending(EXTRACTOR):
                                            self.combinedActions.append(worker.build(EXTRACTOR, vaspene))
                    if self.townhalls.amount >= 6:
                        if (self.units(EXTRACTOR).amount / self.townhalls.amount) < 2:
                            vaspene = vaspenes.random
                            if self.can_afford(EXTRACTOR):
                                worker = self.select_build_worker(vaspene.position)
                                if worker:
                                    if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                                        if not self.already_pending(EXTRACTOR):
                                            self.combinedActions.append(worker.build(EXTRACTOR, vaspene))


    async def macro_decisions(self):
        enemiesNearby = 0
        if self.get_game_time() / 60 > 9:
            self.expand_time = 3.5
        expand_every = self.expand_time * 60
        prefered_base_count = 2 + int(math.floor(self.get_game_time() / expand_every))
        current_base_count = self.townhalls.amount

        if self.minerals > 900:
            prefered_base_count += 1

        location = await self.get_next_expansion()
        enemiesNearby = self.known_enemy_units.filter(
            lambda unit: unit.type_id not in self.units_to_ignore).closer_than(45, location)

        if not (prefered_base_count > current_base_count and current_base_count < 9 and not self.already_pending(
                HATCHERY) and enemiesNearby.amount < 2):
            if self.townhalls.exists:
                if not self.units(SPAWNINGPOOL).exists:
                    if self.can_afford(SPAWNINGPOOL) and not self.already_pending(SPAWNINGPOOL):
                        ws = self.workers.gathering
                        if ws:
                            w = ws.furthest_to(ws.center)
                            loc = await self.find_placement(UnitTypeId.SPAWNINGPOOL, self.townhalls.random.position, placement_step=4)
                            self.combinedActions.append(w.build(SPAWNINGPOOL, loc))

                elif not self.ling_speed:
                    if self.units(SPAWNINGPOOL).exists:
                        rw = self.units(SPAWNINGPOOL).first
                        if rw.noqueue:
                            if await self.has_ability(RESEARCH_ZERGLINGMETABOLICBOOST, rw):
                                if self.can_afford(RESEARCH_ZERGLINGMETABOLICBOOST):
                                    await self.do(rw(RESEARCH_ZERGLINGMETABOLICBOOST))
                                    self.ling_speed = True

                elif not self.units(BANELINGNEST).exists:
                    if self.can_afford(BANELINGNEST) and not self.already_pending(BANELINGNEST):
                        ws = self.workers.gathering
                        if ws:
                            w = ws.furthest_to(ws.center)
                            loc = await self.find_placement(UnitTypeId.BANELINGNEST, self.townhalls.random.position,
                                                            placement_step=4)
                            self.combinedActions.append(w.build(BANELINGNEST, loc))
                elif not (self.units(LAIR).exists or self.units(HIVE).exists or await self.hasLair() or await self.hasHive()):
                    if self.units(HATCHERY).idle.exists:
                        hq = self.units(HATCHERY).idle.random
                        if not await self.hasLair() and self.vespene >= 100:
                            if not (self.units(HIVE).exists or self.units(LAIR).exists):
                                if self.can_afford(LAIR):
                                    self.combinedActions.append(hq.build(LAIR))
                elif self.units(EVOLUTIONCHAMBER).amount + self.already_pending(EVOLUTIONCHAMBER) < 2:
                    if self.can_afford(EVOLUTIONCHAMBER) and self.already_pending(EVOLUTIONCHAMBER) < 2:
                        ws = self.workers.gathering
                        if ws:
                            w = ws.furthest_to(ws.center)
                            loc = await self.find_placement(UnitTypeId.EVOLUTIONCHAMBER, self.townhalls.random.position,
                                                            placement_step=4)
                            self.combinedActions.append(w.build(EVOLUTIONCHAMBER, loc))

                elif not self.bane_speed:
                    if self.units(BANELINGNEST).exists:
                        rw = self.units(BANELINGNEST).first
                        if rw.noqueue:
                            if await self.has_ability(RESEARCH_CENTRIFUGALHOOKS, rw):
                                if self.can_afford(RESEARCH_CENTRIFUGALHOOKS):
                                    await self.do(rw(RESEARCH_CENTRIFUGALHOOKS))
                                    self.bane_speed = True

                elif not self.units(INFESTATIONPIT).exists:
                    if self.can_afford(INFESTATIONPIT) and not self.already_pending(INFESTATIONPIT):
                        ws = self.workers.gathering
                        if ws:
                            w = ws.furthest_to(ws.center)
                            loc = await self.find_placement(UnitTypeId.INFESTATIONPIT, self.townhalls.random.position,
                                                            placement_step=4)
                            self.combinedActions.append(w.build(INFESTATIONPIT, loc))

                elif not self.units(SPIRE).exists and not self.units(GREATERSPIRE).exists:
                    if self.can_afford(SPIRE) and not self.already_pending(SPIRE) and not self.already_pending(GREATERSPIRE):
                        ws = self.workers.gathering
                        if ws:
                            w = ws.furthest_to(ws.center)
                            loc = await self.find_placement(UnitTypeId.SPIRE, self.townhalls.random.position,
                                                            placement_step=4)
                            self.combinedActions.append(w.build(SPIRE, loc))

                elif not self.units(HIVE).exists:
                    if self.units(LAIR).idle.exists:
                        hq = self.units(LAIR).idle.random
                        if not await self.hasHive() and self.vespene >= 150:
                            if not self.units(HIVE).exists:
                                if self.can_afford(HIVE):
                                    self.combinedActions.append(hq.build(HIVE))

                elif not self.crack_ling:
                    if self.units(SPAWNINGPOOL).exists:
                        rw = self.units(SPAWNINGPOOL).first
                        if rw.noqueue:
                            if await self.has_ability(RESEARCH_ZERGLINGADRENALGLANDS, rw):
                                if self.can_afford(RESEARCH_ZERGLINGADRENALGLANDS):
                                    await self.do(rw(RESEARCH_ZERGLINGADRENALGLANDS))
                                    self.crack_ling = True

                elif not self.units(GREATERSPIRE).exists:
                    if self.units(HIVE).exists and self.units(GREATERSPIRE).amount + self.already_pending(GREATERSPIRE) < 1:
                        if self.units(SPIRE).ready.idle.exists:
                            if self.can_afford(GREATERSPIRE):
                                self.combinedActions.append(
                                    self.units(SPIRE).ready.idle.random(UPGRADETOGREATERSPIRE_GREATERSPIRE))

                elif self.units(GREATERSPIRE).exists:
                    evochamber = self.units(GREATERSPIRE).first
                    if evochamber.noqueue:
                        for upgrade_level in range(1, 4):
                            upgrade_armor_id = getattr(sc2.constants,
                                                       "RESEARCH_ZERGFLYERATTACKLEVEL" + str(upgrade_level))
                            upgrade_missle_id = getattr(sc2.constants,
                                                        "RESEARCH_ZERGFLYERARMORLEVEL" + str(upgrade_level))
                            if await self.has_ability(upgrade_missle_id, evochamber):
                                if self.can_afford(upgrade_missle_id):
                                    await self.do(evochamber(upgrade_missle_id))
                            elif await self.has_ability(upgrade_armor_id, evochamber):
                                if self.can_afford(upgrade_armor_id):
                                    await self.do(evochamber(upgrade_armor_id))

                if self.units(EVOLUTIONCHAMBER).exists:
                    evochamber = self.units(EVOLUTIONCHAMBER).first
                    if evochamber.noqueue:
                        for upgrade_level in range(1, 4):
                            upgrade_armor_id = getattr(sc2.constants,
                                                       "RESEARCH_ZERGMELEEWEAPONSLEVEL" + str(upgrade_level))
                            upgrade_missle_id = getattr(sc2.constants,
                                                        "RESEARCH_ZERGGROUNDARMORLEVEL" + str(upgrade_level))
                            if await self.has_ability(upgrade_missle_id, evochamber):
                                if self.can_afford(upgrade_missle_id):
                                    await self.do(evochamber(upgrade_missle_id))
                            elif await self.has_ability(upgrade_armor_id, evochamber):
                                if self.can_afford(upgrade_armor_id):
                                    await self.do(evochamber(upgrade_armor_id))
        ################################################################################################################
        army_units = self.units(ZERGLING) | self.units(BANELING) | self.units(CORRUPTOR) | self.units(BROODLORD) | self.units(QUEEN)
        allowed_supply = 5
        mySupply = 0
        enemySupply = 0
        for unit in army_units:
            mySupply += unit._type_data._proto.food_required

        for tags, type in self.unit_memory.items():
            supply = self._game_data.units[type.value]._proto.food_required
            enemySupply += supply

        # print("Theirs: " + str(enemySupply))
        # print("Theirs: " + str(enemySupply - allowed_supply))
        # print("Mine: " + str(mySupply))

        if enemySupply - allowed_supply > mySupply:
            self.stop_droning = True

        if mySupply > enemySupply:
            self.stop_droning = False



    async def defence(self):
        enemiesNearby = None
        for th in self.townhalls:
            enemiesNearby = self.known_enemy_units.closer_than(15, th.position)
            if self.game_time < 8:
                if enemiesNearby:
                    if self.workers.closer_than(15, enemiesNearby.random.position).amount > enemiesNearby.amount:
                        for worker in self.workers.closer_than(15, enemiesNearby.random.position):
                            if len(self.workers_away) <= enemiesNearby.amount:
                                if worker.tag not in self.workers_away:
                                    target = enemiesNearby.random
                                    self.combinedActions.append(worker.attack(target.position))
                                    self.workers_away.append(worker.tag)
                for h in self.townhalls:
                    for worker in self.workers_away:
                        w = self.workers.find_by_tag(worker)
                        if w:
                            if w.distance_to(h) > 45:
                                self.workers_away.remove(worker)
                                self.combinedActions.append(w.move(self.start_location))

            if enemiesNearby.amount > 2:
                for unit in self.units(QUEEN).idle:
                    self.combinedActions.append(unit.attack(enemiesNearby.random.position))

    async def train_units(self):
        enemiesNearby = 0
        if self.get_game_time() / 60 > 9:
            self.expand_time = 3.5
        expand_every = self.expand_time * 60
        prefered_base_count = 2 + int(math.floor(self.get_game_time() / expand_every))
        current_base_count = self.townhalls.amount

        if self.minerals > 900:
            prefered_base_count += 1

        location = await self.get_next_expansion()
        enemiesNearby = self.known_enemy_units.filter(
            lambda unit: unit.type_id not in self.units_to_ignore).closer_than(45, location)

        if not (prefered_base_count > current_base_count and current_base_count < 9 and not self.already_pending(
                HATCHERY) and enemiesNearby.amount < 2):

            larvae = self.units(LARVA)
            if self.supply_left < 10:
                for larva in larvae:
                    if self.already_pending(OVERLORD) < 2:
                        if self.can_afford(OVERLORD):
                            self.combinedActions.append(larva.train(OVERLORD))

            if not self.stop_droning and self.units(DRONE).amount + self.already_pending(DRONE) < 80:
                if self.can_afford(DRONE):
                    for larva in larvae:
                        self.combinedActions.append(larva.train(DRONE))
            else:
                if self.units(DRONE).amount + self.already_pending(DRONE) < 80 and self.already_pending(DRONE) < 1:
                    if self.can_afford(DRONE):
                        for larva in larvae:
                            self.combinedActions.append(larva.train(DRONE))
                            break

                else:
                    for larva in larvae:
                        if self.can_afford(ZERGLING):
                            self.combinedActions.append(larva.train(ZERGLING))

            for ling in self.units(ZERGLING).ready:
                enemiesNearby = self.known_enemy_units.filter(lambda unit: unit.type_id not in self.units_to_ignore).closer_than(30, ling)
                if not enemiesNearby:
                    if self.units(ZERGLING).amount > 1 and self.units(BANELINGNEST).exists:
                        if ((self.units(BANELING).amount + self.units(BANELINGCOCOON).amount) / self.units(ZERGLING).amount) < 0.3:
                            if self.vespene > 25 and self.minerals > 25:
                                await self.do(ling(MORPHZERGLINGTOBANELING_BANELING))

            if self.townhalls.exists:
                for hq in self.townhalls.noqueue.ready:
                    if self.units(SPAWNINGPOOL).ready.exists:
                        if self.units(QUEEN).amount < (self.townhalls.amount * 1.25):
                            if self.can_afford(QUEEN) and self.units(QUEEN).amount < 10:
                                self.combinedActions.append(hq.train(QUEEN))



    async def remember_units(self):
        for unit in self.known_enemy_units.not_structure.filter(lambda unit: (unit.type_id not in self.units_to_ignore) and (unit.tag not in self.unit_memory)):
            self.unit_memory[unit.tag] = unit.type_id
        for building in self.known_enemy_units.structure:
            if building.tag not in self.structure_memory:
                self.structure_memory[building.tag] = building.type_id


    def split_workers(self):
        """Split the workers on the beginning """
        for drone in self.workers:
            self.combinedActions.append(drone.gather(self.state.mineral_field.closest_to(drone)))


    async def on_unit_destroyed(self, unit_tag):
        if unit_tag in self.unit_memory:
            del self.unit_memory[unit_tag]
        if unit_tag in self.structure_memory:
            del self.structure_memory[unit_tag]
        if unit_tag in self.workers_away:
            self.workers_away.remove(unit_tag)

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

    async def find_placement(self, building, near, max_distance=20, random_alternative=False, placement_step=3,
                             min_distance=0, minDistanceToResources=3):
        """Finds a placement location for building."""

        assert isinstance(building, (AbilityId, UnitTypeId))
        # assert self.can_afford(building)
        assert isinstance(near, Point2)

        if isinstance(building, UnitTypeId):
            building = self._game_data.units[building.value].creation_ability
        else:  # AbilityId
            building = self._game_data.abilities[building.value]

        if await self.can_place(building, near):
            return near

        for distance in range(min_distance, max_distance, placement_step):
            possible_positions = [Point2(p).offset(near).to2 for p in (
                    [(dx, -distance) for dx in range(-distance, distance + 1, placement_step)] +
                    [(dx, distance) for dx in range(-distance, distance + 1, placement_step)] +
                    [(-distance, dy) for dy in range(-distance, distance + 1, placement_step)] +
                    [(distance, dy) for dy in range(-distance, distance + 1, placement_step)]
            )]
            if (
                    self.townhalls | self.state.mineral_field | self.state.vespene_geyser).exists and minDistanceToResources > 0:
                possible_positions = [x for x in possible_positions if
                                      (self.state.mineral_field | self.state.vespene_geyser).closest_to(x).distance_to(
                                          x) >= minDistanceToResources]  # filter out results that are too close to resources

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

    async def hasHive(self):
        if (self.units(HIVE).amount > 0):
            return True
        morphingYet = False
        for h in self.units(LAIR):
            if CANCEL_MORPHHIVE in await self.get_available_abilities(h):
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
            await self.build(townhall, near=location, max_distance=max_distance, random_alternative=False,
                             placement_step=1)

    async def distribute_workers(self, performanceHeavy=True, onlySaturateGas=False):
        # expansion_locations = self.expansion_locations
        # owned_expansions = self.owned_expansions
        if self.townhalls.exists:
            for w in self.workers.idle:
                th = self.townhalls.closest_to(w)
                mfs = self.state.mineral_field.closer_than(10, th)
                if mfs:
                    mf = mfs.closest_to(w)
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
            self.exactExpansionLocations.append(await self.find_placement(HATCHERY, loc, minDistanceToResources=5.5,
                                                                          placement_step=1))  # TODO: change mindistancetoresource so that a hatch still has room to be built

    def inPathingGrid(self, pos):
        # returns True if it is possible for a ground unit to move to pos - doesnt seem to work on ramps or near edges
        assert isinstance(pos, (Point2, Point3, Unit))
        pos = pos.position.to2.rounded
        return self._game_info.pathing_grid[(pos)] != 0

    # stolen and modified from position.py
    def neighbors4(self, position, distance=1):
        p = position
        d = distance
        return {
            Point2((p.x - d, p.y)),
            Point2((p.x + d, p.y)),
            Point2((p.x, p.y - d)),
            Point2((p.x, p.y + d)),
        }

    # stolen and modified from position.py
    def neighbors8(self, position, distance=1):
        p = position
        d = distance
        return self.neighbors4(position, distance) | {
            Point2((p.x - d, p.y - d)),
            Point2((p.x - d, p.y + d)),
            Point2((p.x + d, p.y - d)),
            Point2((p.x + d, p.y + d)),
        }

    def set_game_step(self):
        """It sets the interval of frames that it will take to make the actions, depending of the game situation"""
        if self.ground_enemies:
            if len(self.ground_enemies) >= 15:
                self._client.game_step = 2
            elif len(self.ground_enemies) >= 5:
                self._client.game_step = 4
            else:
                self._client.game_step = 6
        else:
            self._client.game_step = 8

# run_game(maps.get("AcidPlantLE"), [
#     # Human(Race.Zerg),
#     Bot(Race.Zerg, Overmind()),
#     #Bot(Race.Protoss, CannonLoverBot())
#     Computer(Race.Random, Difficulty.VeryHard)
#     # Bot(Race.Random, Trinity()),
# ], realtime=False)


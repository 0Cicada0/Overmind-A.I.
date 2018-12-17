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


    async def on_step(self, iteration):
        self.game_time = self.get_game_time() / 60
        print(self.game_time)
        self.ground_enemies = self.known_enemy_units.not_flying.not_structure
        await self.do_actions(self.combinedActions)
        self.combinedActions = []
        self.iteration = iteration
        if not iteration:
            self.split_workers()
        self.set_game_step()
        await self.remember_units()
        await self.train_units()
        await self.distribute_workers()
        await self.defence()
        await self.macro_decisions()
        await self.buildExtractor()


    ###FUNCTIONS##
    async def getLair(self):
        if self.units(SPAWNINGPOOL).ready.exists:
            if self.units(HATCHERY).idle.exists:
                hq = self.units(HATCHERY).idle.random
                if not await self.hasLair() and self.vespene >= 100:
                    if not (self.units(HIVE).exists or self.units(LAIR).exists):
                        self.droneUp = False
                        self.buildArmy = False
                        self.buildMore = False
                    if not (self.units(HIVE).exists or self.units(LAIR).exists) and self.lingSpeed:
                        if self.can_afford(LAIR):
                            self.combinedActions.append(hq.build(LAIR))
    async def buildExtractor(self):
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
                        if (self.units(EXTRACTOR).amount / self.townhalls.amount) < 1:
                            vaspene = vaspenes.random
                            if self.can_afford(EXTRACTOR):
                                worker = self.select_build_worker(vaspene.position)
                                if worker:
                                    if not self.units(EXTRACTOR).closer_than(1.0, vaspene).exists:
                                        if not self.already_pending(EXTRACTOR):
                                            self.combinedActions.append(worker.build(EXTRACTOR, vaspene))


    async def macro_decisions(self):
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
            elif not (self.units(LAIR).exists or self.units(HIVE).exists):
                if self.units(HATCHERY).idle.exists:
                    hq = self.units(HATCHERY).idle.random
                    if not await self.hasLair() and self.vespene >= 100:
                        if not (self.units(HIVE).exists or self.units(LAIR).exists):
                            if self.can_afford(LAIR):
                                self.combinedActions.append(hq.build(LAIR))
            elif self.units(EVOLUTIONCHAMBER).amount < 2:
                if self.can_afford(EVOLUTIONCHAMBER) and self.already_pending(EVOLUTIONCHAMBER) < 2:
                    ws = self.workers.gathering
                    if ws:
                        w = ws.furthest_to(ws.center)
                        loc = await self.find_placement(UnitTypeId.EVOLUTIONCHAMBER, self.townhalls.random.position,
                                                        placement_step=4)
                        self.combinedActions.append(w.build(EVOLUTIONCHAMBER, loc))
            elif self.melee_upgrades == 0:
                if self.units(EVOLUTIONCHAMBER).exists:
                    for evochamber in self.units(EVOLUTIONCHAMBER).ready:
                        if evochamber.noqueue:
                            if self.has_ability(ZERGMELEEWEAPONSLEVEL1, evochamber):
                                if self.can_afford(ZERGMELEEWEAPONSLEVEL1):
                                    self.combinedActions.append(evochamber(ZERGMELEEWEAPONSLEVEL1))
            elif self.armor_upgrades == 0:
                if self.units(EVOLUTIONCHAMBER).exists:
                    for evochamber in self.units(EVOLUTIONCHAMBER).ready:
                        if evochamber.noqueue:
                            if await self.has_ability(ZERGGROUNDARMORSLEVEL1, evochamber):
                                if self.can_afford(ZERGGROUNDARMORSLEVEL1):
                                    self.combinedActions.append(evochamber(ZERGGROUNDARMORSLEVEL1))
            # elif self.melee_upgrades == 1:
            # elif self.armor_upgrades == 1:
            # elif not self.units(INFESTATIONPIT).exists:
            # elif not self.units(SPIRE).exists:
            # elif not self.units(HIVE).exists:


    async def defence(self):
        enemiesCloseToTh = None
        for th in self.townhalls.ready:
            enemiesCloseToTh = self.known_enemy_units.filter(lambda unit: not unit.is_flying).closer_than(15,
                                                                                                          th.position)
        if enemiesCloseToTh:
            if self.workers.closer_than(15, enemiesCloseToTh.random.position).amount > enemiesCloseToTh.amount:
                i = len(self.workers_away)
                for worker in self.workers.closer_than(15, enemiesCloseToTh.random.position):
                    if i <= enemiesCloseToTh.amount:
                        target = enemiesCloseToTh.random
                        self.combinedActions.append(worker.attack(target.position))
                        self.workers_away.append(worker.tag)
                        i += 1

        for h in self.townhalls:
            for worker in self.workers_away:
                w = self.workers.find_by_tag(worker)
                if w:
                    if w.distance_to(h) > 45:
                        self.workers_away.remove(worker)
                        self.combinedActions.append(w.move(self.start_location))

    async def train_units(self):
        larvae = self.units(LARVA)
        if self.supply_left < 10:
            for larva in larvae:
                if self.already_pending(OVERLORD) < 2:
                    self.combinedActions.append(larva.train(OVERLORD))

        if self.units(DRONE).amount + self.already_pending(DRONE) < 80:
            if self.want == "drone":
                for larva in larvae:
                    self.combinedActions.append(larva.train(DRONE))
            else:
                larva = larvae.first
                self.combinedActions.append(larva.train(DRONE))

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
            del self.unit_memory[unit_tag]
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


"""Independent turn-based six-tank model. NOT the Unity engine or win-rate evidence.

Static rules come from the supplied engine inspection. Authentication, animation,
network scheduling and hidden engine details are outside this model.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import random

DIRS = {"U": (-1, 0), "R": (0, 1), "D": (1, 0), "L": (0, -1)}


@dataclass
class Unit:
    team: str
    slot: int
    pos: tuple
    hp: int = 100
    normal: int = 99
    mega: int = 0
    yellow: int = 0
    turns: int = 0
    facing: str = "R"


class World:
    def __init__(self, map_index=0, seed=0):
        source = Path(__file__).resolve().parents[1] / "engine" / "maps" / "all_maps.json"
        self.terrain = json.loads(source.read_text(encoding="utf-8"))["stage0_map" + str(map_index)]
        self.units = {}
        rng = random.Random(seed)
        for team in ("A", "B"):
            for slot in (1, 2, 3):
                r, c = rng.randrange(12 - slot * 3, 15 - slot * 3), rng.randrange(0, 2)
                if team == "B":
                    r, c = 15 - r, 15 - c
                self.units[team + str(slot)] = Unit(team, slot, (r, c), facing="R" if team == "A" else "L")
        self.turret_hp = {"A": 100, "B": 100}
        self.metrics = {team: dict(actions=0, illegal=0, friendly=0, rock=0,
                                  empty=0, waits=0, supplies=0, shots=0, errors=0)
                        for team in ("A", "B")}
        self.log = []

    def occupied(self, p):
        return next((u for u in self.units.values() if u.hp > 0 and u.pos == p), None)

    def inside(self, p):
        return 0 <= p[0] < 16 and 0 <= p[1] < 16

    def adjacent_supply(self, p):
        return any(self.inside((p[0]+dr,p[1]+dc)) and
                   self.terrain[p[0]+dr][p[1]+dc] == "F" for dr,dc in DIRS.values())

    def state(self, key):
        me = self.units[key]
        grid = [["G" if v in ("G1", "G2") else
                 ("H" if v[1:] == me.team else "X") if v in ("XA", "XB") else v
                 for v in row] for row in self.terrain]
        allies = ["M %d %s %d %d" % (me.hp, me.facing, me.normal, me.mega)]
        enemies = []
        for other_key, other in self.units.items():
            if other_key == key:
                continue
            name = ("M" if other.team == me.team else "E") + str(other.slot)
            (allies if other.team == me.team else enemies).append(name + " " + str(other.hp))
        for other_key, other in self.units.items():
            if other.hp > 0:
                grid[other.pos[0]][other.pos[1]] = "M" if other_key == key else (
                    "M" if other.team == me.team else "E") + str(other.slot)
        allies.append("H " + str(self.turret_hp[me.team]))
        enemies.append("X " + str(self.turret_hp["B" if me.team == "A" else "A"]))
        codes = ["KZDVZJXFCU"] if self.adjacent_supply(me.pos) else []  # TIMEISGOLD
        return "\n".join(["16 16 %d %d %d" % (len(allies),len(enemies),len(codes)),
                          *(" ".join(row) for row in grid), *allies, *enemies, *codes])

    def penalize(self, unit):
        unit.yellow += 1
        self.metrics[unit.team]["illegal"] += 1
        if unit.yellow >= 3:
            unit.hp = 0

    def apply(self, key, command):
        unit = self.units[key]
        if unit.hp <= 0:
            return
        unit.turns += 1
        metric = self.metrics[unit.team]
        metric["actions"] += 1
        self.log.append((key, command))
        parts = command.split()
        if parts == ["S"]:
            metric["waits"] += 1
            self.penalize(unit)
            return
        if parts and parts[0] == "G":
            if (parts == ["G", "TIMEISGOLD"] and self.adjacent_supply(unit.pos) and unit.mega < 10):
                unit.mega += 1
                metric["supplies"] += 1
            else:
                self.penalize(unit)
            return
        if len(parts) < 2 or parts[0] not in DIRS:
            self.penalize(unit)
            return
        direction, action = parts[:2]
        unit.facing = direction
        dr, dc = DIRS[direction]
        if action == "A" and len(parts) == 2:
            q = unit.pos[0]+dr, unit.pos[1]+dc
            if not self.inside(q) or self.occupied(q):
                self.penalize(unit)
                return
            token = self.terrain[q[0]][q[1]]
            forbidden = "G1" if unit.team == "A" else "G2"
            if token not in ("G", "G1", "G2", "S") or token == forbidden:
                self.penalize(unit)
                return
            unit.pos = q
            if token == "S":
                unit.hp = max(0, unit.hp-10)
            return
        if action != "F" or not (len(parts) == 2 or (len(parts) == 3 and parts[2] == "M")):
            self.penalize(unit)
            return
        mega = len(parts) == 3
        if (unit.mega if mega else unit.normal) <= 0:
            metric["empty"] += 1
            self.penalize(unit)
            return
        if mega:
            unit.mega -= 1
        else:
            unit.normal -= 1
        metric["shots"] += 1
        damage = 70 if mega else 30
        crossed_friend = False
        for d in range(1, 4):
            q = unit.pos[0]+dr*d, unit.pos[1]+dc*d
            if not self.inside(q):
                break
            other = self.occupied(q)
            if other:
                if other.team == unit.team:
                    if not crossed_friend:
                        metric["friendly"] += 1
                        crossed_friend = True
                    continue  # Supplied engine passes through own tanks.
                other.hp = max(0, other.hp-damage)
                return
            token = self.terrain[q[0]][q[1]]
            if token == "T":
                self.terrain[q[0]][q[1]] = "G"
                return
            if token in ("XA", "XB"):
                side = token[1]
                if side == unit.team:
                    metric["friendly"] += 1
                self.turret_hp[side] = max(0, self.turret_hp[side]-damage)
                return
            if token in ("R", "F"):
                metric["rock"] += token == "R"
                break
        self.penalize(unit)

    def outcome(self):
        lost = {team: self.turret_hp[team] <= 0 or
                sum(u.hp <= 0 for u in self.units.values() if u.team == team) >= 2
                for team in ("A", "B")}
        if any(lost.values()):
            return "draw" if all(lost.values()) else "B" if lost["A"] else "A"
        return None


def play(world, controllers, rounds=100, first="A"):
    # Explicit simulation convention, not a claim about Unity turn scheduling.
    other = "B" if first == "A" else "A"
    order = [side+str(i) for i in (1,2,3) for side in (first,other)]
    for _ in range(rounds):
        for key in order:
            if world.units[key].hp <= 0:
                continue
            try:
                command = controllers[key].choose(world.state(key))
            except Exception:
                world.metrics[key[0]]["errors"] += 1
                raise
            world.apply(key, command)
            outcome = world.outcome()
            if outcome:
                return outcome
    return "turn_limit"

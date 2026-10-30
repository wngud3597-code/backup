"""Battle SSAFY 1.3 team: one attacker + two home guards. Python 3.9+.

All three teammates can use this single file. Default roles are automatic.
The two tanks starting closest to H guard home; the remaining tank attacks X.
Run it from the game's Python source picker, or run this file with Python.
Importing this module never opens a connection. Rules were checked against the
supplied v1.3 Assembly-CSharp.dll and the v1.1.10 manual.
M/H/X are relative to the player; no fixed A/B side or enemy coordinates.
"""
import argparse
import heapq
import itertools
import json
import math
import select
import socket
import sys
import time
from collections import deque

HOST, PORT = "127.0.0.1", 8747
NICKNAME = "SSAFY_Team"
DIRS = {"U": (-1, 0), "R": (0, 1), "D": (1, 0), "L": (0, -1)}
TRANSPARENT = frozenset(("G", "S", "W"))
ENEMY_TANKS = frozenset(("E1", "E2", "E3"))
FRIEND_TANKS = frozenset(("M1", "M2", "M3", "A1", "A2", "A3"))
SHELLS = {"normal": (30, " F"), "mega": (70, " F M")}
MAX_BYTES = 4 * 1024 * 1024
CONFIG = {
    "cipher_shift": 9,       # Supplied v1.3: encryption +17, decryption +9.
    "forbidden_cells": None,
    "planning_ms": 100,
    "max_expansions": 12000,
}


class ProtocolError(ValueError):
    pass


def header_values(line):
    try:
        values = tuple(map(int, line.split()))
        if len(values) != 5:
            raise ValueError("Header must contain five integers")
        h, w, na, ne, nc = values
        if not (0 < h <= 256 and 0 < w <= 256):
            raise ValueError("Invalid map dimensions")
        if min(na, ne, nc) < 0 or na + ne + nc > 4096:
            raise ValueError("Invalid record counts")
        return values
    except ValueError as exc:
        raise ProtocolError(str(exc)) from exc


def parse_data(data):
    if not isinstance(data, str) or len(data.encode("utf-8")) > MAX_BYTES:
        raise ProtocolError("Invalid or oversized game state")
    lines = data.strip().splitlines()
    if not lines:
        raise ProtocolError("Empty game state")
    h, w, na, ne, nc = header_values(lines[0])
    if len(lines) != 1 + h + na + ne + nc:
        raise ProtocolError("Incomplete game state")
    grid = [line.split() for line in lines[1:1 + h]]
    if any(len(row) != w for row in grid):
        raise ProtocolError("Invalid map row")

    def records(rows):
        result = {}
        for line in rows:
            parts = line.split()
            if len(parts) < 2 or parts[0] in result:
                raise ProtocolError("Invalid unit record")
            result[parts[0]] = parts[1:]
        return result

    start = 1 + h
    allies = records(lines[start:start + na])
    enemies = records(lines[start + na:start + na + ne])
    if set(allies) & set(enemies):
        raise ProtocolError("Duplicate ally/enemy ID")
    return grid, allies, enemies, lines[start + na + ne:]


def decode_cipher(cipher, shift=9):
    if type(shift) is not int or not 0 <= shift < 26:
        raise ValueError("Cipher shift must be an integer from 0 to 25")
    if not cipher or any(not "A" <= ch <= "Z" for ch in cipher):
        raise ProtocolError("Cipher must contain uppercase A-Z only")
    return "".join(chr((ord(ch) - 65 + shift) % 26 + 65) for ch in cipher)


def infer_cipher_shift(cipher, plaintext):
    matches = [s for s in range(26) if decode_cipher(cipher, s) == plaintext]
    if len(matches) != 1:
        raise ValueError("Cipher/plaintext pair does not define one Caesar shift")
    return matches[0]


def salvo(hp, normal, mega):
    """Fewest shots, then fewest mega shells. None if total damage is short."""
    if hp <= 0:
        return 0, 0, 0
    choices = []
    for m in range(min(mega, (hp + 69) // 70) + 1):
        n = max(0, (hp - 70 * m + 29) // 30)
        if n <= normal:
            choices.append((n + m, m, n))
    return min(choices) if choices else None


def weapon_for(hp, normal, mega):
    plan = salvo(hp, normal, mega)
    if plan:
        return "mega" if plan[1] else "normal"
    return "mega" if mega else "normal" if normal else None


def clear_trees(count, normal, mega):
    # Both shells clear a tree in one shot. Preserve the stronger shell.
    used_normal = min(count, normal)
    used_mega = count - used_normal
    if used_mega > mega:
        return None
    return normal - used_normal, mega - used_mega


class Bot:
    def __init__(self, config=None):
        self.config = dict(CONFIG)
        if config:
            unknown = set(config) - set(CONFIG)
            if unknown:
                raise ValueError("Unknown configuration: " + str(unknown))
            self.config.update(config)
        shift = self.config["cipher_shift"]
        if shift is not None:
            decode_cipher("A", shift)
        budget = self.config["planning_ms"]
        if type(budget) not in (int, float) or not math.isfinite(budget) or budget <= 0:
            raise ValueError("planning_ms must be positive")
        if type(self.config["max_expansions"]) is not int or self.config["max_expansions"] < 1:
            raise ValueError("max_expansions must be a positive integer")
        cells = self.config["forbidden_cells"]
        if cells is not None and (not isinstance(cells, list) or any(
                not isinstance(p, (list, tuple)) or len(p) != 2 or
                any(type(v) is not int for v in p) for p in cells)):
            raise ValueError("forbidden_cells must be a list of [row, column]")
        self.recent = deque(maxlen=16)
        self.previous = None
        self.failed_moves = {}
        self.supply_failed = False
        self.last_decision = {}

    def inside(self, p):
        return 0 <= p[0] < self.h and 0 <= p[1] < self.w

    def cell(self, p, cleared=0):
        token = self.grid[p[0]][p[1]]
        if token == "M" or (token == "T" and cleared & self.tree_bits[p]):
            return "G"
        return token

    def _forbidden_area(self):
        explicit = self.config["forbidden_cells"]
        if explicit is not None:
            return {tuple(p) for p in explicit}
        # v1.3 hides G1/G2 home tiles as G in the network map. Standard battle
        # maps put H in a corner. No invented 5x5 ban for an interior stage H.
        result = set()
        for r, c in self.positions.get("H", []):
            if r in (0, self.h - 1) and c in (0, self.w - 1):
                rows = range(min(3, self.h)) if r == 0 else range(max(0, self.h - 3), self.h)
                cols = range(min(3, self.w)) if c == 0 else range(max(0, self.w - 3), self.w)
                result.update((i, j) for i in rows for j in cols)
        return result

    def load(self, data):
        self.grid, self.allies, self.enemies, self.codes = parse_data(data)
        self.h, self.w = len(self.grid), len(self.grid[0])
        self.positions = {}
        for r, row in enumerate(self.grid):
            for c, token in enumerate(row):
                self.positions.setdefault(token, []).append((r, c))
        if len(self.positions.get("M", [])) != 1 or "M" not in self.allies:
            raise ProtocolError("Missing own tank M")
        self.pos = self.positions["M"][0]
        try:
            own = self.allies["M"]
            if len(own) != 4 or own[1] not in DIRS:
                raise ValueError("Invalid own tank record")
            self.hp, self.normal, self.mega = int(own[0]), int(own[2]), int(own[3])
            self.enemy_hp = {k: int(v[0]) for k, v in self.enemies.items()}
            if min(self.hp, self.normal, self.mega) < 0 or self.mega > 10:
                raise ValueError("Invalid own health/ammunition")
            if any(v < 0 for v in self.enemy_hp.values()):
                raise ValueError("Invalid enemy health")
        except (ValueError, IndexError) as exc:
            raise ProtocolError(str(exc)) from exc
        self.tree_bits = {p: 1 << i for i, p in enumerate(self.positions.get("T", []))}
        self.blocked = self._forbidden_area()
        if self.previous:
            command, old_pos, old_mega, destination = self.previous
            if command.endswith(" A"):
                if self.pos == old_pos:
                    self.failed_moves[destination] = self.failed_moves.get(destination, 0) + 1
                else:
                    self.failed_moves.clear()
            elif command.startswith("G "):
                self.supply_failed = self.mega <= old_mega
        self.previous = None
        self.blocked.update(p for p, count in self.failed_moves.items() if count >= 1)
        self.threat_map = self.threats()

    def ray(self, p, direction, cleared=0):
        """First blocker; also block friends, even though engine permits passage."""
        dr, dc = DIRS[direction]
        for distance in range(1, 4):
            q = p[0] + dr * distance, p[1] + dc * distance
            if not self.inside(q):
                break
            token = self.cell(q, cleared)
            if token not in TRANSPARENT:
                return token, q
        return None

    def threats(self):
        exposed = {}
        for key in ENEMY_TANKS:
            if self.enemy_hp.get(key, 0) <= 0:
                continue
            for origin in self.positions.get(key, []):
                for dr, dc in DIRS.values():
                    for distance in range(1, 4):
                        p = origin[0] + dr * distance, origin[1] + dc * distance
                        if not self.inside(p):
                            break
                        token = self.cell(p)
                        if token in TRANSPARENT:
                            exposed.setdefault(p, set()).add(key)
                        elif token in ENEMY_TANKS:
                            continue  # Enemy shells pass through their allies.
                        else:
                            break
        return exposed

    def risk(self, p, hp=None):
        count = len(self.threat_map.get(p, ()))
        remaining = self.hp if hp is None else hp
        # Enemy ammunition is not sent: tactical cost, not predicted damage.
        return count * (0.8 + (4.0 if remaining <= 70 else 0.0))

    def movable(self, p):
        return (self.inside(p) and p not in self.blocked and
                self.cell(p) in {"G", "S"} and
                (self.cell(p) != "S" or self.hp > 10))

    def adjacent_supply(self, p):
        return any(self.inside((p[0] + dr, p[1] + dc)) and
                   self.cell((p[0] + dr, p[1] + dc)) == "F" for dr, dc in DIRS.values())

    def supply_answer(self):
        shift = self.config["cipher_shift"]
        if (shift is None or self.supply_failed or self.mega >= 10 or
                not self.codes or not self.adjacent_supply(self.pos)):
            return None
        return decode_cipher(self.codes[0], shift)

    def validate(self, command):
        if command == "S":
            return True  # Emergency only: this gives a battle yellow card.
        parts = command.split()
        if len(parts) == 2 and parts[0] == "G":
            answer = self.supply_answer()
            return answer is not None and parts[1] == answer
        if len(parts) < 2 or parts[0] not in DIRS:
            return False
        direction, kind = parts[:2]
        if kind == "A" and len(parts) == 2:
            dr, dc = DIRS[direction]
            return self.movable((self.pos[0] + dr, self.pos[1] + dc))
        if kind != "F" or not (len(parts) == 2 or (len(parts) == 3 and parts[2] == "M")):
            return False
        stock = self.mega if len(parts) == 3 else self.normal
        hit = self.ray(self.pos, direction)
        return bool(stock and hit and (hit[0] == "T" or
                    (hit[0] in ENEMY_TANKS | {"X"} and self.enemy_hp.get(hit[0], 0) > 0)))

    def expired(self):
        return (self.expansions >= self.config["max_expansions"] or
                time.perf_counter() >= self.deadline)

    def finish_options(self, p, normal, mega, cleared, target):
        """Firing lanes after clearing only trees directly before target."""
        hp = self.enemy_hp.get(target, 0)
        if hp <= 0:
            return
        for direction, (dr, dc) in DIRS.items():
            trees = 0
            for distance in range(1, 4):
                q = p[0] + dr * distance, p[1] + dc * distance
                if not self.inside(q):
                    break
                token = self.cell(q, cleared)
                if token == "T":
                    trees += 1
                    continue
                if token == target:
                    stock = clear_trees(trees, normal, mega)
                    attack = salvo(hp, *stock) if stock else None
                    if attack:
                        weapon = ("normal" if normal else "mega") if trees else weapon_for(hp, normal, mega)
                        yield trees + attack[0], direction + SHELLS[weapon][1], trees, attack
                    break
                if token not in TRANSPARENT:
                    break

    def plan(self, target):
        """Bounded A*: movement + real tree shots + supply + target salvo.

        Positions, shells, cleared trees and sand damage are in the search state.
        Replan from the actual received map every turn.
        """
        target_positions = self.positions.get(target, [])
        if not target_positions or self.enemy_hp.get(target, 0) <= 0:
            return None
        tr, tc = target_positions[0]
        allow_supply = self.config["cipher_shift"] is not None and not self.supply_failed
        serial = itertools.count()

        def heuristic(p):
            return max(0, abs(p[0] - tr) + abs(p[1] - tc) - 3) + 1

        # lower bound, cost, tie breaker, position, shells, cleared, loss,
        # first actual command, number of actual actions so far
        heap = [(heuristic(self.pos), 0.0, next(serial), self.pos,
                 self.normal, self.mega, 0, 0, "", 0)]
        labels = {(self.pos, self.normal, self.mega, 0): [(0.0, 0)]}
        best = None
        while heap and not self.expired():
            lower, cost, _, p, normal, mega, cleared, loss, first, turns = heapq.heappop(heap)
            if best and lower >= best["cost"]:
                break
            key = (p, normal, mega, cleared)
            if (cost, loss) not in labels.get(key, ()):
                continue
            self.expansions += 1
            for tail_turns, fire, tree_count, attack in self.finish_options(p, normal, mega, cleared, target):
                total = cost + tail_turns * (1 + self.risk(p, self.hp - loss))
                command = first or fire
                if (not best or total < best["cost"]) and self.validate(command):
                    best = {"command": command, "cost": total, "turns": turns + tail_turns,
                            "goal": p, "target": target, "sand_damage": loss,
                            "last_lane_trees": tree_count, "salvo": attack}

            edges = []
            for direction, (dr, dc) in DIRS.items():
                q = p[0] + dr, p[1] + dc
                if not self.inside(q) or q in self.blocked:
                    continue
                token = self.cell(q, cleared)
                n2, m2, mask2 = normal, mega, cleared
                loss2 = loss + (10 if token == "S" else 0)
                if loss2 >= self.hp:
                    continue
                if token in {"G", "S"}:
                    action, duration = direction + " A", 1
                elif token == "T":
                    stock = clear_trees(1, normal, mega)
                    if stock is None:
                        continue
                    n2, m2 = stock
                    mask2 |= self.tree_bits[q]
                    action = direction + SHELLS["normal" if normal else "mega"][1]
                    duration = 2
                else:
                    continue
                edge_cost = (duration + (loss2 - loss) * 0.06 +
                             self.risk(q, self.hp - loss2) +
                             (self.risk(p, self.hp - loss) if duration == 2 else 0))
                if not first:
                    edge_cost += 0.12 * self.recent.count(q)
                edges.append((q, n2, m2, mask2, loss2, action, duration, edge_cost))
            if allow_supply and mega < 10 and self.adjacent_supply(p):
                answer = self.supply_answer() if p == self.pos else None
                # Future plaintext comes from a fresh frame, never a stale code.
                if p != self.pos or answer is not None:
                    action = "G " + answer if answer else ""
                    edges.append((p, normal, mega + 1, cleared, loss, action, 1,
                                  1 + self.risk(p, self.hp - loss)))
            for q, n2, m2, mask2, loss2, action, duration, edge_cost in edges:
                first2 = first or action
                if not first2:
                    continue
                cost2 = cost + edge_cost
                lower2 = cost2 + heuristic(q)
                if best and lower2 >= best["cost"]:
                    continue
                key2 = (q, n2, m2, mask2)
                old = labels.setdefault(key2, [])
                if any(c <= cost2 and damage <= loss2 for c, damage in old):
                    continue
                labels[key2] = [(c, damage) for c, damage in old
                                if not (c >= cost2 and damage >= loss2)] + [(cost2, loss2)]
                heapq.heappush(heap, (lower2, cost2, next(serial), q, n2, m2,
                                      mask2, loss2, first2, turns + duration))
        return best

    def _nearby_shots(self):
        result = []
        for direction in DIRS:
            hit = self.ray(self.pos, direction)
            if hit and hit[0] in ENEMY_TANKS | {"X"}:
                hp = self.enemy_hp.get(hit[0], 0)
                weapon = weapon_for(hp, self.normal, self.mega)
                if hp > 0 and weapon:
                    command = direction + SHELLS[weapon][1]
                    if self.validate(command):
                        result.append((hit[0], hp, command, weapon, hit[1]))
        return result

    def fallback(self, target):
        for key, hp, command, weapon, pos in self._nearby_shots():
            if key == "X":
                return command, "turret_damage"
        answer = self.supply_answer()
        if answer:
            return "G " + answer, "supply"

        # Cheap Dijkstra still gives progress if resource search hit its budget.
        supply_goals = set()
        if self.normal * 30 + self.mega * 70 < self.enemy_hp.get(target, 0):
            for p in ((r, c) for r in range(self.h) for c in range(self.w)):
                if self.cell(p) in {"G", "S"} and self.adjacent_supply(p):
                    supply_goals.add(p)
        goals = supply_goals
        if not goals:
            for direction, (dr, dc) in DIRS.items():
                for origin in self.positions.get(target, []):
                    for d in range(1, 4):
                        p = origin[0] + dr * d, origin[1] + dc * d
                        if not self.inside(p):
                            break
                        token = self.cell(p)
                        if token in {"G", "S"} and p not in self.blocked:
                            goals.add(p)
                        if token not in TRANSPARENT:
                            break
        heap = [(0.0, self.pos, 0, "")]
        labels = {self.pos: [(0.0, 0)]}
        fallback_deadline = time.perf_counter() + 0.02
        while heap and time.perf_counter() < fallback_deadline:
            cost, p, loss, first = heapq.heappop(heap)
            if (cost, loss) not in labels.get(p, ()):
                continue
            if p in goals and first:
                return first, "safe_route_fallback"
            for direction, (dr, dc) in DIRS.items():
                q = p[0] + dr, p[1] + dc
                if not self.inside(q) or q in self.blocked or self.cell(q) not in {"G", "S"}:
                    continue
                loss2 = loss + (10 if self.cell(q) == "S" else 0)
                if loss2 >= self.hp:
                    continue
                cost2 = cost + 1 + (loss2 - loss) * 0.06 + self.risk(q, self.hp - loss2)
                old = labels.setdefault(q, [])
                if any(c <= cost2 and damage <= loss2 for c, damage in old):
                    continue
                labels[q] = [(c, damage) for c, damage in old
                             if not (c >= cost2 and damage >= loss2)] + [(cost2, loss2)]
                heapq.heappush(heap, (cost2, q, loss2, first or direction + " A"))
        moves = []
        targets = self.positions.get(target, [])
        for direction, (dr, dc) in DIRS.items():
            q = self.pos[0] + dr, self.pos[1] + dc
            if self.movable(q):
                distance = min((abs(q[0] - r) + abs(q[1] - c) for r, c in targets), default=0)
                score = 4 * self.risk(q) + self.recent.count(q) * 3 + distance * 0.1
                moves.append((score, direction + " A"))
        if moves:
            return min(moves)[1], "reposition"
        # If boxed in, one adjacent tree may be the only way to preserve a live
        # tank without receiving a yellow card. This is an escape, not random
        # tree shooting while a usable movement route exists.
        for direction, (dr, dc) in DIRS.items():
            q = self.pos[0] + dr, self.pos[1] + dc
            if self.inside(q) and q not in self.blocked and self.cell(q) == "T":
                weapon = "normal" if self.normal else "mega" if self.mega else None
                if weapon and self.validate(direction + SHELLS[weapon][1]):
                    return direction + SHELLS[weapon][1], "clear_escape_tree"
        # No penalty-free action exists when trapped without usable ammunition.
        return "S", "trapped_no_safe_action"

    def choose(self, data):
        started = time.perf_counter()
        self.load(data)
        self.deadline = started + self.config["planning_ms"] / 1000
        self.expansions = 0
        target = "X" if self.enemy_hp.get("X", 0) > 0 else next(
            (k for k in sorted(ENEMY_TANKS) if self.enemy_hp.get(k, 0) > 0), None)
        command, reason, route = None, "", None
        shots = self._nearby_shots()
        wins = [s for s in shots if s[0] == "X" and s[1] <= SHELLS[s[3]][0]]
        tanks = [s for s in shots if s[0] in ENEMY_TANKS]
        if wins:
            command, reason = wins[0][2], "destroy_turret_now"
        elif tanks:
            shot = min(tanks, key=lambda s: (
                s[1] > SHELLS[s[3]][0],
                (salvo(s[1], self.normal, self.mega) or (999,))[0], s[1], s[0]))
            command, reason, target = shot[2], "engage_visible_tank", shot[0]
        elif target:
            route = self.plan(target)
            if route:
                command, reason = route["command"], "planned_turret_attack" if target == "X" else "stage_attack"
        if command is None:
            command, reason = self.fallback(target)
        if not self.validate(command):
            command, reason = "S", "safety_guard_no_safe_action"
        destination = None
        if command.endswith(" A"):
            dr, dc = DIRS[command[0]]
            destination = self.pos[0] + dr, self.pos[1] + dc
        self.previous = (command, self.pos, self.mega, destination)
        self.recent.append(self.pos)
        self.last_decision = {
            "command": command, "reason": reason, "target": target,
            "expansions": self.expansions, "planning_truncated": self.expired(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "route": route, "emergency_wait": command == "S",
        }
        return command


def is_end_signal(text):
    return text.strip() in {"0", "-1", "0 0 0 0 0"}


def receive(sock, framing="official"):
    """Accumulate fragments; v1.3 has no final LF or frame length.

    A 10ms local quiet check after shape validation catches split final fields.
    No receiver can guarantee framing of arbitrarily delayed data without a
    server delimiter. `lines` is for a server that adds a final newline.
    """
    if framing not in {"official", "lines"}:
        raise ValueError("Unknown framing")
    raw = bytearray()
    deadline = None
    complete = False
    while len(raw) < MAX_BYTES:
        timeout = 0.01 if complete else (None if deadline is None else max(0.0, deadline - time.perf_counter()))
        ready, _, _ = select.select([sock], [], [], timeout)
        if not ready:
            if complete:
                return text
            raise ProtocolError("Timed out receiving an incomplete game state")
        chunk = sock.recv(min(65536, MAX_BYTES - len(raw)))
        if not chunk:
            if not raw:
                return None
            if complete:
                return text
            raise ProtocolError("Connection closed inside a game state")
        raw.extend(chunk)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            if exc.reason == "unexpected end of data":
                complete = False
                continue
            raise ProtocolError("Invalid UTF-8 game state") from exc
        # Other players' turns have no client timeout. Limit only a partial
        # response, below the game's six-second battle command deadline.
        deadline = time.perf_counter() + 5.0
        if is_end_signal(text):
            return None
        try:
            parse_data(text)
        except ProtocolError:
            complete = False
        else:
            complete = framing == "official" or text.endswith("\n")
    raise ProtocolError("Game state exceeds size limit")


def wire_command(command, prefix=""):
    if not command or any(ch in command + prefix for ch in ("\r", "\n", "\x00")):
        raise ProtocolError("Invalid outgoing command")
    return (prefix + command + " ").encode("utf-8")


def run(bot, nickname=NICKNAME, prefix="", host=HOST, port=PORT, framing="official"):
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.settimeout(None)
        sock.sendall(wire_command("INIT " + nickname, prefix))
        while True:
            data = receive(sock, framing)
            if data is None:
                return
            command = bot.choose(data)
            if not bot.validate(command):
                raise ProtocolError("Outgoing safety check failed")
            if command == "S":
                print("[WARNING] No safe action; S gives a battle yellow card.", file=sys.stderr)
            sock.sendall(wire_command(command, prefix))



class TeamBot(Bot):
    """One attacker, two home guards; uses Bot's tested protocol and attack engine."""

    def __init__(self, config=None, role="auto"):
        super().__init__(config)
        if role not in {"auto", "attack", "defend1", "defend2"}:
            raise ValueError("Unknown team role")
        self.requested_role = role
        self.assigned_role = None
        self.role = None
        self.unit_index = None
        self.assignment_source = None
        self.guard_pairs = []
        self.guard_signature = None

    @staticmethod
    def distance(p, q):
        return abs(p[0] - q[0]) + abs(p[1] - q[1])

    def _live_friends(self):
        return {key: points[0] for key, points in self.positions.items()
                if key == "M" or (key in FRIEND_TANKS and
                                  int(self.allies.get(key, [100])[0]) > 0)}

    def _assign_role(self):
        home = self.positions.get("H", [None])[0]
        friends = self._live_friends()
        if self.assigned_role is None:
            if self.requested_role != "auto":
                self.assigned_role = self.requested_role
                self.assignment_source = "explicit_role"
            else:
                # Actual v1.3 spawns have disjoint bands. Earlier players may
                # have already moved before another tank receives its first M.
                # Infer our immutable identity from our own untouched spawn.
                native = ((self.h, self.w) == (16, 16) and
                          home in {(15, 0), (0, 15)} and
                          self.positions.get("X", [None])[0] == (15 - home[0], 15 - home[1]))
                vertical = abs(self.pos[0] - home[0]) if home else -1
                horizontal = abs(self.pos[1] - home[1]) if home else -1
                if native and horizontal <= 1 and 4 <= vertical <= 12:
                    self.unit_index = (vertical - 4) // 3 + 1
                    self.assigned_role = ("defend1", "defend2", "attack")[self.unit_index - 1]
                    self.assignment_source = "verified_spawn_band"
                elif home and len(friends) > 1:
                    order = sorted(friends, key=lambda key: (self.distance(friends[key], home), friends[key]))
                    rank = order.index("M")
                    self.assigned_role = "defend" + str(rank + 1) if rank < min(2, len(order) - 1) else "attack"
                    self.assignment_source = "initial_home_distance"
                else:
                    self.assigned_role = "attack"
                    self.assignment_source = "single_or_stage"
        self.role = self.assigned_role
        if self.requested_role == "auto" and self.unit_index is not None:
            live_ids = {self.unit_index}
            live_ids.update(int(key[1:]) for key in friends
                            if key.startswith("M") and key[1:] in {"1", "2", "3"})
            # Attack succession uses stable IDs, never the moving coordinates.
            intruders = bool(home) and any(self.enemy_hp.get(key, 0) > 0 and
                            any(self.distance(p, home) <= 10 for p in self.positions.get(key, []))
                            for key in ENEMY_TANKS)
            successor = self.unit_index == max(live_ids)
            self.role = ("attack" if successor and
                         (self.assigned_role == "attack" or not intruders)
                         else "defend" + str(self.unit_index))
        if not home or (self.requested_role == "auto" and
                        (len(friends) <= 1 or not any(
                            self.enemy_hp.get(key, 0) > 0 for key in ENEMY_TANKS))):
            self.role = "attack"

    def _terrain(self, p):
        token = self.grid[p[0]][p[1]]
        return "G" if token == "M" or token in FRIEND_TANKS | ENEMY_TANKS else token

    def _view(self, p):
        """Stable terrain coverage. Actual shots always use ray + validate."""
        seen = set()
        for dr, dc in DIRS.values():
            for step in range(1, 4):
                q = p[0] + dr * step, p[1] + dc * step
                if not self.inside(q):
                    break
                seen.add(q)
                if self._terrain(q) not in TRANSPARENT:
                    break
        return seen

    def _refresh_pairs(self, home):
        zone = self._forbidden_area()
        local = [(r, c) for r in range(self.h) for c in range(self.w)
                 if self.distance((r, c), home) <= 10]
        signature = (home, tuple((p, self._terrain(p)) for p in local), tuple(sorted(zone)))
        if signature == self.guard_signature:
            return
        self.guard_signature = signature
        fire = {p for p in self._view(home) if self._terrain(p) in {"G", "S"}}
        approach = {q for p in fire for dr, dc in DIRS.values()
                    for q in [(p[0] + dr, p[1] + dc)] if self.inside(q)} - fire
        self.guard_fire, self.guard_approach = fire, approach
        cells = {p for p in local if self.distance(p, home) <= 7 and
                 p not in zone and self._terrain(p) == "G"}
        views = {p: self._view(p) for p in cells}

        def coverage(seen):
            return len(seen & fire) + 0.4 * len(seen & approach)

        candidates = []
        for p in sorted(cells):
            for dr, dc in ((0, 1), (1, 0)):
                q = p[0] + dr, p[1] + dc
                if q in cells:
                    a, b = coverage(views[p]), coverage(views[q])
                    score = 2 * min(a, b) + 0.5 * (a + b) - 0.03 * self.distance(p, home)
                    candidates.append((score, p, q, views[p] | views[q]))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        self.guard_pairs = []
        if candidates:
            first = candidates[0]
            self.guard_pairs.append((first[1], first[2]))
            others = [item for item in candidates if not ({item[1], item[2]} & {first[1], first[2]})]
            if others:
                second = min(others, key=lambda item: (
                    -(coverage(item[3] | first[3]) + 0.3 * item[0]), item[1], item[2]))
                self.guard_pairs.append((second[1], second[2]))

    def _guard_route(self, goals, home, reserved=(), radius=None):
        """Bounded A*: account for cumulative sand HP and actual tree ammo."""
        radius = max(10, self.distance(self.pos, home)) if radius is None else radius
        goals = {p for p in goals if self.inside(p) and p not in self.blocked and
                 self.cell(p) in {"G", "S"}}
        if not goals or self.pos in goals:
            return None
        serial = itertools.count()
        heuristic = lambda p: min(self.distance(p, goal) for goal in goals)
        heap = [(heuristic(self.pos), 0.0, next(serial), self.pos,
                 self.normal, self.mega, 0, 0, "")]
        labels = {(self.pos, self.normal, self.mega, 0): [(0.0, 0)]}
        limit = min(self.deadline, time.perf_counter() + 0.04)
        while heap and not self.expired() and time.perf_counter() < limit:
            _, cost, _, p, normal, mega, cleared, loss, first = heapq.heappop(heap)
            if (cost, loss) not in labels.get((p, normal, mega, cleared), ()):
                continue
            self.expansions += 1
            if p in goals and first and self.validate(first):
                return {"command": first, "cost": cost, "goal": p, "sand_damage": loss}
            for direction, (dr, dc) in DIRS.items():
                q = p[0] + dr, p[1] + dc
                if (not self.inside(q) or q in self.blocked or q in reserved or
                        self.distance(q, home) > radius):
                    continue
                token = self.cell(q, cleared)
                loss2 = loss + (10 if token == "S" else 0)
                if loss2 >= self.hp:
                    continue
                n2, m2, mask2, duration = normal, mega, cleared, 1
                if token in {"G", "S"}:
                    action = direction + " A"
                elif token == "T":
                    stock = clear_trees(1, normal, mega)
                    if stock is None:
                        continue
                    n2, m2 = stock
                    mask2 |= self.tree_bits[q]
                    duration = 2
                    action = direction + SHELLS["normal" if normal else "mega"][1]
                else:
                    continue
                command = first or action
                cost2 = cost + duration + (loss2 - loss) * 0.08 + self.risk(q, self.hp - loss2)
                key = q, n2, m2, mask2
                old = labels.setdefault(key, [])
                if any(value <= cost2 and damage <= loss2 for value, damage in old):
                    continue
                labels[key] = [(value, damage) for value, damage in old
                               if not (value >= cost2 and damage >= loss2)] + [(cost2, loss2)]
                heapq.heappush(heap, (cost2 + heuristic(q), cost2, next(serial),
                                      q, n2, m2, mask2, loss2, command))
        return None

    def _guard_action(self, home, slot):
        self._refresh_pairs(home)
        pair = self.guard_pairs[slot] if slot < len(self.guard_pairs) else ()
        reserved = {p for index, points in enumerate(self.guard_pairs) if index != slot for p in points}
        enemies = {key: points[0] for key, points in self.positions.items()
                   if key in ENEMY_TANKS and self.enemy_hp.get(key, 0) > 0}
        near = min((self.distance(p, home) for p in enemies.values()), default=999)
        shots = self._nearby_shots()
        tanks = [shot for shot in shots if shot[0] in ENEMY_TANKS]
        if tanks:
            shot = min(tanks, key=lambda item: (
                item[4] not in self.guard_fire, self.distance(item[4], home),
                item[1] > SHELLS[item[3]][0], item[1], item[0]))
            return shot[2], "guard_engage_tank", None, shot[0]
        if shots:
            return shots[0][2], "guard_visible_turret", None, shots[0][0]
        if (near > 10 and self.mega < 2 and
                self.config["cipher_shift"] is not None and not self.supply_failed):
            answer = self.supply_answer()
            if answer:
                return "G " + answer, "guard_safe_supply", None, None
            supply_goals = set()
            for f in self.positions.get("F", []):
                if self.distance(f, home) > 16 or (pair and min(self.distance(f, p) for p in pair) > 9):
                    continue
                for dr, dc in DIRS.values():
                    supply_goals.add((f[0] + dr, f[1] + dc))
            route = self._guard_route(supply_goals, home, reserved, radius=16)
            if route:
                return route["command"], "guard_reach_supply", route, None
        # During an intrusion, prefer a one-step firing lane close to our post.
        interception = []
        if near <= 5 and self.pos in pair and (self.normal or self.mega):
            for direction, (dr, dc) in DIRS.items():
                q = self.pos[0] + dr, self.pos[1] + dc
                if (not self.movable(q) or q in reserved or self.distance(q, home) > 7 or
                        (pair and min(self.distance(q, p) for p in pair) > 2)):
                    continue
                for facing in DIRS:
                    hit = self.ray(q, facing)
                    if hit and hit[0] in enemies:
                        interception.append((self.distance(hit[1], home), self.risk(q),
                                             self.enemy_hp[hit[0]], direction + " A", hit[0]))
            if interception:
                best = min(interception)
                return best[3], "guard_intercept_lane", None, best[4]
        if self.pos in pair:
            other = pair[1] if self.pos == pair[0] else pair[0]
            for direction, (dr, dc) in DIRS.items():
                if (self.pos[0] + dr, self.pos[1] + dc) == other and self.movable(other):
                    return direction + " A", "guard_patrol_pair", None, None
        route = self._guard_route(pair, home, reserved)
        if route:
            return route["command"], "guard_reach_post", route, None
        moves = []
        for direction, (dr, dc) in DIRS.items():
            q = self.pos[0] + dr, self.pos[1] + dc
            if self.movable(q) and q not in reserved and self.distance(q, home) <= max(10, self.distance(self.pos, home)):
                distance = min((self.distance(q, p) for p in pair), default=self.distance(q, home))
                score = 4 * self.risk(q) + 5 * (self.cell(q) == "S") + distance + self.recent.count(q) * 0.3
                moves.append((score, direction + " A"))
        if moves:
            return min(moves)[1], "guard_safe_reposition", None, None
        # A tree shot is legal; rocks, allies, supplies and empty lanes never are.
        for direction, (dr, dc) in DIRS.items():
            q = self.pos[0] + dr, self.pos[1] + dc
            if self.inside(q) and q not in self.blocked and self.cell(q) == "T":
                weapon = "normal" if self.normal else "mega" if self.mega else None
                if weapon and self.validate(direction + SHELLS[weapon][1]):
                    return direction + SHELLS[weapon][1], "guard_clear_escape_tree", None, None
        return "S", "guard_trapped_no_safe_action", None, None

    def choose(self, data):
        started = time.perf_counter()
        self.load(data)
        self._assign_role()
        if self.role == "attack":
            command = super().choose(data)
        else:
            self.deadline = started + self.config["planning_ms"] / 1000
            self.expansions = 0
            slot = int(self.role[-1]) - 1
            command, reason, route, target = self._guard_action(self.positions["H"][0], slot)
            if not self.validate(command):
                command, reason = "S", "guard_safety_no_safe_action"
            destination = None
            if command.endswith(" A"):
                dr, dc = DIRS[command[0]]
                destination = self.pos[0] + dr, self.pos[1] + dc
            self.previous = command, self.pos, self.mega, destination
            self.recent.append(self.pos)
            self.last_decision = {"command": command, "reason": reason, "target": target,
                                  "route": route, "expansions": self.expansions,
                                  "planning_truncated": self.expired(),
                                  "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                                  "emergency_wait": command == "S"}
        self.last_decision.update({"role": self.role, "assigned_role": self.assigned_role,
                                   "unit_index": self.unit_index,
                                   "assignment_source": self.assignment_source,
                                   "guard_pair": (self.guard_pairs[int(self.role[-1]) - 1]
                                                  if self.role != "attack" and
                                                  int(self.role[-1]) <= len(self.guard_pairs) else None)})
        return command


_default_bot = None


def my_func(game_data):
    """Official-template hook: output = my_func(game_data)."""
    global _default_bot
    if _default_bot is None:
        _default_bot = TeamBot()
    return _default_bot.choose(game_data)


def main():
    parser = argparse.ArgumentParser(description="Battle SSAFY v1.3 team: 1 attacker + 2 guards (Python 3.9+)")
    parser.add_argument("launcher_prefix", nargs="?", default="")
    parser.add_argument("--nickname", default=NICKNAME)
    parser.add_argument("--role", choices=("auto", "attack", "defend1", "defend2"), default="auto")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--transport", choices=("official", "lines"), default="official")
    parser.add_argument("--replay", help="Read one UTF-8 state file without connecting")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--cipher-shift", type=int, default=CONFIG["cipher_shift"])
    parser.add_argument("--cipher-pair", nargs=2, metavar=("CIPHER", "PLAINTEXT"))
    parser.add_argument("--forbidden-cells", help="Override hidden home tiles with a JSON [[row,col],...] file")
    args = parser.parse_args()
    if args.cipher_pair:
        print(infer_cipher_shift(*args.cipher_pair))
        return
    config = {"cipher_shift": args.cipher_shift}
    if args.forbidden_cells:
        with open(args.forbidden_cells, encoding="utf-8-sig") as file:
            config["forbidden_cells"] = json.load(file)
    bot = TeamBot(config, role=args.role)
    if args.replay:
        with open(args.replay, encoding="utf-8-sig") as file:
            print(bot.choose(file.read()))
        if args.explain:
            print(json.dumps(bot.last_decision, ensure_ascii=False), file=sys.stderr)
    else:
        run(bot, args.nickname, args.launcher_prefix, args.host, args.port, args.transport)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print("[ERROR]", exc, file=sys.stderr)
        sys.exit(1)

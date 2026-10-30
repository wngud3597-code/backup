"""TeamBattle DEFENDER for a two-defender/one-attacker team.
Manual v1.1.10 + current competition FAQ/yellow-card rules.
No stage mode, guessed initial HP/ammo, shared team files, or extra sockets.
"""
import argparse
import copy
import heapq
import json
import math
import socket
import sys
import time
from collections import deque

HOST, PORT = '127.0.0.1', 8747
NICKNAME = '지역반_이름'
DIRS = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}
MAX_CELLS, MAX_RECORDS, MAX_BYTES = 65536, 4096, 4*1024*1024
# Confirmed: manual pp.59-67, current team competition instructions.
# None means unknown, never an implicit zero or an invented rule.
RULES = {'self_id': 'M',
 'friendly_tank_tokens': ['M1', 'M2', 'M3'],
 'friendly_turret_tokens': ['H'],
 'enemy_tank_tokens': ['E1', 'E2', 'E3'],
 'enemy_turret_tokens': ['X'],
 'walkable': ['G', 'S'],
 'transparent': ['G', 'S', 'W'],
 'terrain_damage': {'G': 0, 'S': 10},
 'destructible': ['T'],
 'forbidden_offsets': None,
 'forbidden_cells': [],
 'enemy_hp_index': 0,
 'shells': {'normal': {'ammo_index': 2, 'range': 3, 'damage': 30, 'suffix': ' F', 'cost': 0},
            'mega': {'ammo_index': 3, 'range': 3, 'damage': 70, 'suffix': ' F M', 'cost': 18}},
 'supply': {'shift': None, 'gain': None},
 'planning_ms': 40,
 'max_expansions': 6000,
 'patrol': {'mode': 'always', 'radius': 2, 'chase_radius': 3, 'max_span': 3, 'switch_margin': 8},
 'transport': {'framing': None, 'connect_timeout': 5, 'read_timeout': None}}

class ProtocolError(ValueError):
    pass

class ConfigurationError(ValueError):
    pass

class NoLegalAction(RuntimeError):
    pass


def header_values(line):
    try:
        fields = line.split()
        if len(fields) != 5:
            raise ValueError('Header requires five integers')
        h, w, na, ne, nc = map(int, fields)
        if min(h, w) < 1 or h*w > MAX_CELLS or min(na, ne, nc) < 0 or na+ne+nc > MAX_RECORDS:
            raise ValueError('Invalid dimensions/counts or local input limit exceeded')
        return h, w, na, ne, nc
    except ValueError as exc:
        raise ProtocolError(str(exc)) from exc


def parse_data(data):
    if not isinstance(data, str) or len(data) > MAX_BYTES:
        raise ProtocolError('Expected bounded text state')
    lines = data.strip().splitlines()
    if not lines:
        raise ProtocolError('Empty state')
    h, w, na, ne, nc = header_values(lines[0])
    if len(lines) != 1+h+na+ne+nc:
        raise ProtocolError('Wrong record count')
    grid = [line.split() for line in lines[1:1+h]]
    if any(len(row) != w for row in grid):
        raise ProtocolError('Wrong map width')
    def records(rows):
        result = {}
        for row in rows:
            parts = row.split()
            if len(parts) < 2 or parts[0] in result:
                raise ProtocolError('Missing or duplicate entity record')
            result[parts[0]] = parts[1:]
        return result
    a = 1+h
    allies, enemies = records(lines[a:a+na]), records(lines[a+na:a+na+ne])
    if set(allies) & set(enemies):
        raise ProtocolError('Entity belongs to both teams')
    return grid, allies, enemies, lines[a+na+ne:]


def decode_cipher(cipher, shift):
    if not isinstance(shift, int) or isinstance(shift, bool) or not 0 <= shift < 26:
        raise ConfigurationError('Confirm a Caesar shift in 0..25 for this match')
    if not cipher or any(not ('A' <= ch <= 'Z') for ch in cipher):
        raise ProtocolError('Expected uppercase Caesar ciphertext')
    return ''.join(chr((ord(ch)-65+shift) % 26+65) for ch in cipher)


def infer_cipher_shift(cipher, plaintext):
    if len(cipher) != len(plaintext) or not cipher:
        raise ValueError('Known cipher/plaintext lengths must match')
    shifts = [s for s in range(26) if decode_cipher(cipher, s) == plaintext]
    if len(shifts) != 1:
        raise ValueError('Pair does not define one Caesar shift')
    return shifts[0]


def merge_rules(override=None):
    result = copy.deepcopy(RULES)
    if override is not None:
        if not isinstance(override, dict):
            raise ConfigurationError('Rules must be an object')
        def merge(dst, src):
            for key, value in src.items():
                if key not in dst:
                    raise ConfigurationError('Unknown rule setting: '+str(key))
                if isinstance(value, dict) and isinstance(dst.get(key), dict):
                    merge(dst[key], value)
                else:
                    dst[key] = copy.deepcopy(value)
        merge(result, override)
    for key in ('self_id', 'friendly_tank_tokens', 'friendly_turret_tokens',
                'enemy_tank_tokens', 'enemy_turret_tokens', 'walkable', 'transparent',
                'terrain_damage', 'destructible', 'enemy_hp_index'):
        if result[key] != RULES[key]:
            raise ConfigurationError('Setting conflicts with manual: '+key)
    if result['self_id'] != 'M':
        raise ConfigurationError('TeamBattle v1.1.10 self ID is M; M1/M2/M3 are allies')
    if result['forbidden_offsets'] is not None:
        if not isinstance(result['forbidden_offsets'], list):
            raise ConfigurationError('Forbidden offsets must be a list or null')
        for offset in result['forbidden_offsets']:
            if not isinstance(offset, (list, tuple)) or len(offset) != 2 or any(type(v) is not int for v in offset):
                raise ConfigurationError('Forbidden offsets require integer pairs')
    if not isinstance(result['forbidden_cells'], list):
        raise ConfigurationError('Forbidden cells must be a list')
    for cell in result['forbidden_cells']:
        if not isinstance(cell, (list, tuple)) or len(cell) != 2 or any(type(v) is not int for v in cell):
            raise ConfigurationError('Forbidden cells require integer pairs')
    # Shell stats are fixed by the manual, not editable guesses from past versions.
    if not isinstance(result['shells'], dict):
        raise ConfigurationError('Shells must be an object')
    def finite_number(value, minimum=0):
        return type(value) in (int,float) and math.isfinite(value) and value >= minimum
    for name, ammo, damage, suffix in [('normal',2,30,' F'), ('mega',3,70,' F M')]:
        shell = result['shells'][name]
        if not isinstance(shell, dict):
            raise ConfigurationError('Shell must be an object: '+name)
        if (shell['ammo_index'], shell['range'], shell['damage'], shell['suffix']) != (ammo,3,damage,suffix):
            raise ConfigurationError('Shell configuration conflicts with manual p.64')
        if not finite_number(shell['cost']):
            raise ConfigurationError('Shell cost must be finite and nonnegative')
    if result['walkable'] != ['G', 'S'] or set(result['transparent']) != {'G','S','W'} or result['terrain_damage'] != {'G':0,'S':10}:
        raise ConfigurationError('Terrain configuration conflicts with manual p.61')
    supply = result['supply']
    if supply is not None and not isinstance(supply, dict):
        raise ConfigurationError('Supply must be an object or null')
    if supply and supply.get('shift') is not None:
        decode_cipher('A', supply['shift'])
    if supply and supply.get('gain') is not None and (type(supply['gain']) is not int or supply['gain'] <= 0):
        raise ConfigurationError('Supply gain must be a positive integer or null')
    if not finite_number(result['planning_ms']) or type(result['max_expansions']) is not int or result['max_expansions'] < 1:
        raise ConfigurationError('Invalid local planning budget')
    patrol = result['patrol']
    if not isinstance(patrol,dict) or patrol['mode'] not in ('always','off'):
        raise ConfigurationError('This defender uses patrol mode always or off; no defender election')
    if type(patrol['radius']) is not int or not 1 <= patrol['radius'] <= 10:
        raise ConfigurationError('Patrol radius must be an integer in 1..10')
    if type(patrol['max_span']) is not int or not 2 <= patrol['max_span'] <= 10:
        raise ConfigurationError('Patrol max_span must be an integer in 2..10')
    if type(patrol['chase_radius']) is not int or not patrol['radius'] <= patrol['chase_radius'] <= 10:
        raise ConfigurationError('Chase radius must be an integer between patrol radius and 10')
    if not finite_number(patrol['switch_margin']):
        raise ConfigurationError('Patrol switch margin must be finite and nonnegative')
    transport = result['transport']
    if not isinstance(transport, dict) or transport['framing'] not in (None,'lines'):
        raise ConfigurationError('Unknown transport framing')
    for key in ('connect_timeout','read_timeout'):
        value = transport[key]
        if value is not None and (not finite_number(value) or value == 0):
            raise ConfigurationError('Transport timeouts must be positive or null')
    return result


class Bot:
    def __init__(self, rules=None):
        self.rules = merge_rules(rules)
        self.recent = deque(maxlen=12)
        self.target = None
        self.dead_enemies, self.dead_allies = set(), set()
        self.last_decision = {}
        self.previous_supply = None
        self.supply_failed = False
        self.supply_observations = []
        self.post_kill_threats = {}
        self.patrol_lane = None
        self.patrol_endpoint = None
        self.defending = False
        self.patrol_status = 'inactive'
        self.defense_anchor = None
        self.tracked_target = None
        self.motion_radius = self.rules['patrol']['radius']

    def load(self, data):
        self.post_kill_threats = {}
        self.grid, self.allies, self.enemies, self.codes = parse_data(data)
        self.positions = {}
        for r, row in enumerate(self.grid):
            for c, token in enumerate(row):
                self.positions.setdefault(token, []).append((r,c))
        for key in self.rules['friendly_tank_tokens']+self.rules['enemy_tank_tokens']:
            if len(self.positions.get(key,())) > 1:
                raise ProtocolError('Duplicate tank map ID: '+key)
        found = self.positions.get('M', [])
        if len(found) != 1 or 'M' not in self.allies:
            raise ProtocolError('Exactly one M map cell and M ally record are required')
        self.pos, self.info = found[0], self.allies['M']
        try:
            if len(self.info) != 4 or self.info[1] not in DIRS:
                raise ValueError('M must have HP, direction, normal ammo, mega ammo')
            self.hp, self.normal, self.mega = int(self.info[0]), int(self.info[2]), int(self.info[3])
            if self.hp <= 0 or min(self.normal,self.mega) < 0 or self.mega > 10:
                raise ValueError('Invalid self HP/ammo')
            for records in (self.allies, self.enemies):
                for key, values in records.items():
                    if int(values[0]) < 0 or (key != 'M' and len(values) != 1):
                        raise ValueError('Other entities provide HP only')
        except (IndexError, ValueError) as exc:
            raise ProtocolError(str(exc)) from exc
        self.enemy_hp = {key:int(value[0]) for key,value in self.enemies.items()}
        self.ally_hp = {key:int(value[0]) for key,value in self.allies.items()}
        if self.defense_anchor is None:
            self.defense_anchor = self.pos
        if (self.tracked_target not in self.rules['enemy_tank_tokens'] or
                self.enemy_hp.get(self.tracked_target,0) <= 0 or
                not self.positions.get(self.tracked_target) or self.normal+self.mega == 0):
            self.tracked_target = None
        if self.tracked_target and min(self._anchor_distance(p) for p in self.positions[self.tracked_target]) > self.rules['patrol']['chase_radius']+3:
            # Triangle bound: even a zero-budget fallback can prove that a target
            # beyond the movement leash plus firing range cannot be engaged.
            self.tracked_target = None
        self.motion_radius = (self.rules['patrol']['chase_radius']
                              if self.tracked_target or self._anchor_distance(self.pos) > self.rules['patrol']['radius']
                              else self.rules['patrol']['radius'])
        # Absence is never interpreted as destruction. Only an explicit HP=0 record.
        for key in self.rules['enemy_tank_tokens']:
            if self.enemy_hp.get(key) == 0:
                self.dead_enemies.add(key)
        for key in self.rules['friendly_tank_tokens']:
            if self.ally_hp.get(key) == 0:
                self.dead_allies.add(key)
        self.blocked = {tuple(p) for p in self.rules['forbidden_cells']}
        offsets = self.rules['forbidden_offsets']
        turrets = [p for key in self.rules['friendly_turret_tokens'] for p in self.positions.get(key, ())]
        self.movement_unknown = bool(turrets and offsets is None and not self.rules['forbidden_cells'])
        if offsets is not None:
            for r,c in turrets:
                self.blocked.update((r+dr,c+dc) for dr,dc in offsets)
        if self.previous_supply:
            old_mega, shift = self.previous_supply
            gain = self.mega-old_mega
            self.supply_observations.append({'shift':shift, 'observed_delta':gain, 'at_cap':self.mega == 10})
            self.supply_failed = gain <= 0
            self.previous_supply = None

    def inside(self, p):
        return 0 <= p[0] < len(self.grid) and 0 <= p[1] < len(self.grid[0])

    def tile_damage(self, p):
        return self.rules['terrain_damage'].get(self.grid[p[0]][p[1]], 0)

    def movable(self, p):
        return (not self.movement_unknown and self.inside(p) and p not in self.blocked
                and self.grid[p[0]][p[1]] in self.rules['walkable'] and self._within_defense_area(p))

    def _anchor_distance(self, p):
        return abs(p[0]-self.defense_anchor[0])+abs(p[1]-self.defense_anchor[1])

    def _within_defense_area(self, p):
        distance = self._anchor_distance(p)
        current = self._anchor_distance(self.pos)
        # Bound every path edge and fallback. An externally displaced unit may
        # move inward to restore the invariant, never farther from its station.
        return distance <= self.motion_radius or (current > self.motion_radius and distance < current)

    def hit(self, p, direction, distance=3, vacate_self=False):
        dr,dc = DIRS[direction]
        for step in range(1,distance+1):
            q = p[0]+dr*step,p[1]+dc*step
            if not self.inside(q):
                return None
            if vacate_self and q == self.pos:
                continue
            cell = self.grid[q[0]][q[1]]
            # Unknown terrain and all allies block conservatively.
            if cell not in self.rules['transparent']:
                return cell,q
        return None

    def is_target(self, key):
        return key in self.rules['enemy_tank_tokens']+self.rules['enemy_turret_tokens'] and self.enemy_hp.get(key,0) > 0

    def supply_answer(self):
        supply = self.rules['supply']
        if not supply or supply.get('shift') is None or self.supply_failed or self.mega >= 10 or not self.codes:
            return None
        adjacent = [(self.pos[0]+dr,self.pos[1]+dc) for dr,dc in DIRS.values()]
        if not any(self.inside(p) and self.grid[p[0]][p[1]] == 'F' for p in adjacent):
            return None
        try:
            return decode_cipher(self.codes[0], supply['shift'])
        except ProtocolError:
            return None

    def actions(self):
        result = []
        for direction,(dr,dc) in DIRS.items():
            p = self.pos[0]+dr,self.pos[1]+dc
            # Lethal sand is a legal engine move but excluded by team survival policy.
            if self.movable(p) and self.tile_damage(p) < self.hp:
                result.append((direction+' A','move',p,None,None))
            hit = self.hit(self.pos,direction)
            if hit and (self.is_target(hit[0]) or hit[0] in self.rules['destructible']):
                for name,shell in self.rules['shells'].items():
                    if int(self.info[shell['ammo_index']]) > 0:
                        result.append((direction+shell['suffix'],'fire',hit[1],hit[0],name))
        answer = self.supply_answer()
        if answer is not None:
            result.append(('G '+answer,'supply',self.pos,None,None))
        return result

    def validate(self, command):
        # Independent grammar/resource/collision check immediately before sending.
        if not isinstance(command,str):
            return False
        parts = command.split()
        if len(parts) == 2 and parts[0] == 'G':
            return parts[1] == self.supply_answer()
        if len(parts) < 2 or parts[0] not in DIRS:
            return False
        direction = parts[0]
        if parts[1:] == ['A']:
            dr,dc = DIRS[direction]
            p = self.pos[0]+dr,self.pos[1]+dc
            return self.movable(p) and self.tile_damage(p) < self.hp
        if parts[1:] not in (['F'],['F','M']):
            return False
        name = 'mega' if len(parts) == 3 else 'normal'
        shell = self.rules['shells'][name]
        if int(self.info[shell['ammo_index']]) <= 0:
            return False
        hit = self.hit(self.pos,direction,shell['range'])
        return bool(hit and (self.is_target(hit[0]) or hit[0] in self.rules['destructible']))

    def salvo(self, hp, normal=None, mega=None):
        """Minimum available mixed-ammo shots; None if current stock cannot finish."""
        normal = self.normal if normal is None else normal
        mega = self.mega if mega is None else mega
        options = []
        for m in range(min(mega, math.ceil(hp/70))+1):
            n = max(0, math.ceil((hp-70*m)/30))
            if n <= normal:
                options.append((n+m,m,n))
        return min(options) if options else None

    def is_winning_shot(self, action):
        if action[1] != 'fire' or not self.is_target(action[3]):
            return False
        hp = self.enemy_hp[action[3]]
        damage = self.rules['shells'][action[4]]['damage']
        return hp <= damage and (action[3] in self.rules['enemy_turret_tokens'] or len(self.dead_enemies) >= 1)

    def _expired(self):
        return time.perf_counter() >= self.deadline or self.expansions >= self.rules['max_expansions']

    def _threats(self, eliminated=None):
        result = {}
        for key in self.rules['enemy_tank_tokens']:
            if self.enemy_hp.get(key,0) <= 0 or key == eliminated:
                continue
            for r,c in self.positions.get(key,()):
                for dr,dc in DIRS.values():
                    for n in range(1,4):
                        p = r+dr*n,c+dc*n
                        if not self.inside(p):
                            break
                        result.setdefault(p,set()).add(key)
                        # Vacate M for conservative destination threat estimation.
                        cell = self.grid[p[0]][p[1]]
                        if p != self.pos and cell != eliminated and cell not in self.rules['transparent']:
                            break
        return result

    def _danger(self, p, eliminated=None):
        if eliminated:
            if eliminated not in self.post_kill_threats:
                self.post_kill_threats[eliminated] = self._threats(eliminated)
            attackers = self.post_kill_threats[eliminated].get(p,set())
        else:
            attackers = self.threats.get(p,set())
        hp = self.hp-(self.tile_damage(p) if p != self.pos else 0)
        # Enemy ammunition/direction/order are unavailable: exposure is a risk bound.
        danger = 24*len(attackers)
        if attackers and hp <= 70*len(attackers):
            danger += 70 if not self.dead_allies else 420
        return danger

    def _reachable(self):
        # Dijkstra with nondominated (cost, cumulative sand loss) labels.
        labels, best, heap = {self.pos:[(0,0)]}, {self.pos:0}, [(0,0,self.pos)]
        while heap and not self._expired():
            cost,loss,p = heapq.heappop(heap)
            if (cost,loss) not in labels[p]:
                continue
            self.expansions += 1
            for dr,dc in DIRS.values():
                q = p[0]+dr,p[1]+dc
                if not self.movable(q):
                    continue
                loss2 = loss+self.tile_damage(q)
                if loss2 >= self.hp:
                    continue
                cost2 = cost+1+self.tile_damage(q)*0.3+len(self.threats.get(q,()))*0.6
                existing = labels.setdefault(q,[])
                if any(c <= cost2 and damage <= loss2 for c,damage in existing):
                    continue
                labels[q] = [(c,d) for c,d in existing if not (c >= cost2 and d >= loss2)]+[(cost2,loss2)]
                best[q] = min(best.get(q,math.inf),cost2)
                heapq.heappush(heap,(cost2,loss2,q))
        return best

    def _support(self, key):
        # Current firing geometry only; does not invent allied ammo or a future action.
        count = 0
        for ally in self.rules['friendly_tank_tokens']:
            if self.ally_hp.get(ally,0) <= 0:
                continue
            for p in self.positions.get(ally,()):
                if any((hit := self.hit(p,d)) and hit[0] == key for d in DIRS):
                    count += 1
        return count

    def _path_cost(self, start, goals):
        loss = self.tile_damage(start)
        if loss >= self.hp:
            return math.inf
        labels,heap = {start:[(0,loss)]},[(0,loss,start)]
        while heap and not self._expired():
            cost,loss,p = heapq.heappop(heap)
            if (cost,loss) not in labels[p]:
                continue
            if p in goals:
                return cost
            self.expansions += 1
            for dr,dc in DIRS.values():
                q = p[0]+dr,p[1]+dc
                if not self.movable(q):
                    continue
                loss2 = loss+self.tile_damage(q)
                if loss2 >= self.hp:
                    continue
                cost2 = cost+1+self.tile_damage(q)*0.3+len(self.threats.get(q,()))*0.6
                existing = labels.setdefault(q,[])
                if any(c <= cost2 and d <= loss2 for c,d in existing):
                    continue
                labels[q] = [(c,d) for c,d in existing if not (c >= cost2 and d >= loss2)]+[(cost2,loss2)]
                heapq.heappush(heap,(cost2,loss2,q))
        return math.inf

    def _goal_distances(self, positions):
        # Forward search per immediate move preserves cumulative sand HP costs.
        result = {}
        if not positions:
            return result
        for dr,dc in DIRS.values():
            p = self.pos[0]+dr,self.pos[1]+dc
            if self.movable(p) and self.tile_damage(p) < self.hp:
                result[p] = self._path_cost(p,positions)
        return result

    def _score(self, action, costs, goal_kind):
        command,kind,p,key,name = action
        if kind == 'fire':
            shell = self.rules['shells'][name]
            if self.is_target(key):
                hp,damage = self.enemy_hp[key],shell['damage']
                kill = hp <= damage
                win = self.is_winning_shot(action)
                eliminated = key if kill else None
                defense = 0
                for ally in ['H']+self.rules['friendly_tank_tokens']:
                    for ap in self.positions.get(ally,()):
                        if key in self.threats.get(ap,()):
                            defense += 30 if not kill else 90
                return (1000000 if win else 0)+200+min(hp,damage)*0.7+120*kill+18*(key == self.target)+10*self._support(key)+defense-shell['cost']-self._danger(self.pos,eliminated)
            return (12 if goal_kind == 'tree' else -80)-shell['cost']-self._danger(self.pos)
        if kind == 'supply':
            # Spend a turn only when stock is low or it improves a reachable salvo.
            return (25 if self.normal+self.mega == 0 else 5 if self.mega == 0 else -80)-self._danger(self.pos)
        route = costs.get(p)
        # An unreachable attack route must not suppress a life-saving retreat.
        progress = -6*min(route,20) if route is not None else -120 if costs else 0
        return progress-self.tile_damage(p)*6-self._danger(p)-12*self.recent.count(p)

    def _home_distance(self, p):
        # Fixed station, not the unconfirmed end-of-match distance metric.
        return self._anchor_distance(p)

    def _patrol_tile(self, p):
        if self.movement_unknown or not self.inside(p) or p in self.blocked:
            return False
        # M is the current occupied endpoint only. On the next observation its
        # vacated tile must be G before we plan to enter it again.
        return (p == self.pos or self.grid[p[0]][p[1]] == 'G') and self._home_distance(p) <= self.rules['patrol']['radius']

    def _patrol_candidates(self, routes):
        cells = set()
        radius = self.rules['patrol']['radius']
        for hr,hc in self.home_positions:
            for r in range(max(0,hr-radius),min(len(self.grid),hr+radius+1)):
                for c in range(max(0,hc-radius),min(len(self.grid[0]),hc+radius+1)):
                    p = r,c
                    if p in routes and self._patrol_tile(p):
                        cells.add(p)
        candidates = set()
        span = self.rules['patrol']['max_span']
        for axis,dr,dc in [('rows',1,0),('cols',0,1)]:
            for p in sorted(cells):
                if (p[0]-dr,p[1]-dc) in cells:
                    continue
                run = []
                q = p
                while q in cells:
                    run.append(q)
                    q = q[0]+dr,q[1]+dc
                length = min(len(run),span)
                if length < 2:
                    continue
                for start in range(len(run)-length+1):
                    candidates.add((axis,tuple(run[start:start+length])))
        return candidates

    def _home_approaches(self):
        points = set()
        for hr,hc in self.home_positions:
            for dr,dc in DIRS.values():
                for n in range(1,4):
                    p = hr+dr*n,hc+dc*n
                    if not self.inside(p):
                        break
                    cell = self.grid[p[0]][p[1]]
                    if cell in ('G','S','M') or cell in self.rules['enemy_tank_tokens']:
                        points.add(p)
                    if cell not in self.rules['transparent'] and cell != 'M':
                        break
        return points

    def _covers(self, p, q):
        if p == q or (p[0] != q[0] and p[1] != q[1]):
            return False
        distance = abs(p[0]-q[0])+abs(p[1]-q[1])
        if distance > 3:
            return False
        dr = (q[0] > p[0])-(q[0] < p[0])
        dc = (q[1] > p[1])-(q[1] < p[1])
        for step in range(1,distance):
            r,c = p[0]+dr*step,p[1]+dc*step
            if (r,c) != self.pos and self.grid[r][c] not in self.rules['transparent']:
                return False
        return True

    def _patrol_action(self, actions, routes):
        self.patrol_status = 'inactive'
        cfg = self.rules['patrol']
        self.home_positions = [self.defense_anchor]
        if cfg['mode'] == 'off' or not self.home_positions or self.movement_unknown or self.normal+self.mega == 0:
            self.defending = False
            return None
        lanes = self._patrol_candidates(routes)
        if not lanes or self._expired():
            self.defending = False
            return None
        approaches = self._home_approaches()
        def lane_score(lane):
            cells = lane[1]
            coverage = sum(any(self._covers(p,q) for p in cells) for q in approaches)
            risk = sum(self._danger(p) for p in cells)/len(cells)
            return coverage*4+len(cells)*2-min(routes[p] for p in cells)*2-risk*0.5
        best = max(lanes,key=lambda lane:(lane_score(lane),lane))
        if self.patrol_lane in lanes and lane_score(best) <= lane_score(self.patrol_lane)+cfg['switch_margin']:
            best = self.patrol_lane
        if best != self.patrol_lane:
            self.patrol_lane = best
            self.patrol_endpoint = None
        self.defending = True
        cells = best[1]
        moves = {a[2]:a for a in actions if a[1] == 'move'}
        if self.pos in cells:
            if self.patrol_endpoint not in (cells[0],cells[-1]):
                self.patrol_endpoint = max((cells[0],cells[-1]),key=lambda p:(abs(p[0]-self.pos[0])+abs(p[1]-self.pos[1]),p))
            if self.pos == self.patrol_endpoint:
                self.patrol_endpoint = cells[-1] if self.pos == cells[0] else cells[0]
            i = cells.index(self.pos)
            j = cells.index(self.patrol_endpoint)
            wanted = moves.get(cells[i+(1 if j > i else -1)])
            self.patrol_status = 'patrol'
        else:
            costs = self._goal_distances(set(cells))
            reachable = [a for a in moves.values() if math.isfinite(costs.get(a[2],math.inf))]
            if not reachable:
                self.defending = False
                return None
            wanted = min(reachable,key=lambda a:(costs[a[2]]+self.tile_damage(a[2])*0.3+self._danger(a[2]),a[0]))
            self.patrol_status = 'approach'
        if wanted is None:
            self.defending = False
            return None
        def score(action):
            if action == wanted:
                # Ignore generic revisit penalties for deliberate endpoint patrol.
                return 40-self.tile_damage(action[2])*6-self._danger(action[2])
            return self._score(action,{},None)
        chosen = max(actions,key=lambda a:(score(a),a[0]))
        if chosen[1] == 'fire':
            self.patrol_status = 'intercept'
            self.target = chosen[3]
        elif chosen != wanted:
            self.patrol_status = 'evade' if chosen[1] == 'move' else 'supply'
        else:
            self.target = None
        return chosen

    def _acquire_target(self, actions):
        candidates = [a for a in actions if a[1] == 'fire' and a[3] in self.rules['enemy_tank_tokens']]
        if self.tracked_target is None and candidates:
            selected = max(candidates,key=lambda a:(self._score(a,{},None),a[0]))
            self.tracked_target = selected[3]
        self.motion_radius = (self.rules['patrol']['chase_radius']
                              if self.tracked_target or self._anchor_distance(self.pos) > self.rules['patrol']['radius']
                              else self.rules['patrol']['radius'])

    def _defense_fallback_score(self, action):
        if action[1] != 'move':
            return self._score(action,{},None)
        p = action[2]
        cost = self.tile_damage(p)*6+self._danger(p)+self.recent.count(p)*4
        if self.tracked_target:
            hit_next = any((hit := self.hit(p,d,vacate_self=True)) and hit[0] == self.tracked_target for d in DIRS)
            target_positions = self.positions.get(self.tracked_target,())
            distance = min((abs(p[0]-r)+abs(p[1]-c) for r,c in target_positions),default=0)
            return (40 if hit_next else -3*distance)-cost
        if self._anchor_distance(self.pos) > self.rules['patrol']['radius']:
            return -10*self._anchor_distance(p)-cost
        return -cost

    def _pursuit_action(self, actions, routes):
        target = self.tracked_target
        if target is None:
            return None
        positions = set()
        for p in routes:
            if self._expired():
                break
            self.expansions += 1
            if any((hit := self.hit(p,d,vacate_self=p != self.pos)) and hit[0] == target for d in DIRS):
                positions.add(p)
        if not positions:
            if not self._expired():
                # Target cannot be engaged from the bounded defense area.
                self.tracked_target = None
            return None
        self.target = target
        costs = self._goal_distances(positions)
        def score(action):
            if action[1] == 'move' and math.isfinite(costs.get(action[2],math.inf)):
                p = action[2]
                return 40-2*min(costs[p],20)-self._danger(p)-self.tile_damage(p)*6
            return self._defense_fallback_score(action)
        chosen = max(actions,key=lambda a:(score(a),a[0]))
        self.patrol_status = 'intercept' if chosen[1] == 'fire' else 'pursue'
        self.defending = True
        return chosen

    def _return_action(self, actions, routes):
        if self._anchor_distance(self.pos) <= self.rules['patrol']['radius']:
            return None
        goals = {p for p in routes if self._anchor_distance(p) <= self.rules['patrol']['radius'] and self.grid[p[0]][p[1]] == 'G'}
        costs = self._goal_distances(goals)
        moves = [a for a in actions if a[1] == 'move' and math.isfinite(costs.get(a[2],math.inf))]
        if not moves:
            return None
        preferred = min(moves,key=lambda a:(costs[a[2]]+self._danger(a[2])+self.tile_damage(a[2])*6,a[0]))
        chosen = max(actions,key=lambda a:((40-self._danger(a[2])-self.tile_damage(a[2])*6) if a == preferred else self._defense_fallback_score(a),a[0]))
        self.patrol_status = 'return' if chosen[1] == 'move' else 'intercept'
        return chosen

    def choose(self, data):
        started = time.perf_counter()
        self.load(data)
        self.deadline = started+self.rules['planning_ms']/1000
        self.expansions = 0
        self.threats = self._threats()
        self.post_kill_threats = {}
        self._acquire_target(self.actions())
        actions = self.actions()
        if not actions:
            reason = 'unresolved H forbidden area' if self.movement_unknown else 'blocked defense area, no ammunition, unknown cipher, or only lethal sand'
            raise NoLegalAction('No approved non-penalty candidate: '+reason)
        # An already validated fallback exists before optional path planning begins.
        fallback = max(actions,key=lambda a:(self._defense_fallback_score(a),a[0]))
        immediate = [a for a in actions if self.is_winning_shot(a)]
        self.patrol_status = 'inactive'
        if immediate:
            chosen = max(immediate,key=lambda a:(self._score(a,{},None),a[0]))
            self.target = chosen[3]
            self.patrol_status = 'winning_attack'
        else:
            chosen = None
            if not self._expired():
                routes = self._reachable()
                chosen = self._pursuit_action(actions,routes)
                if chosen is None and self.tracked_target is None:
                    # Narrow back to the station after abandoning a target. Do not
                    # reuse chase actions outside the newly active patrol radius.
                    self.motion_radius = (self.rules['patrol']['chase_radius']
                                          if self._anchor_distance(self.pos) > self.rules['patrol']['radius']
                                          else self.rules['patrol']['radius'])
                    actions = self.actions()
                    if not actions:
                        raise NoLegalAction('No valid action after returning to defense bounds')
                    fallback = max(actions,key=lambda a:(self._defense_fallback_score(a),a[0]))
                    routes = {p:cost for p,cost in routes.items() if self._within_defense_area(p)}
                    chosen = self._return_action(actions,routes)
                if chosen is None:
                    chosen = self._patrol_action(actions,routes)
            if chosen is None:
                chosen = fallback
                self.patrol_status = ('pursue' if self.tracked_target else 'return'
                                      if self._anchor_distance(self.pos) > self.rules['patrol']['radius'] else 'local_fallback')
        if not self.validate(chosen[0]):
            if not self.validate(fallback[0]):
                raise NoLegalAction('Final validation rejected candidates')
            chosen = fallback
        if chosen[1] == 'fire' and chosen[3] in self.rules['enemy_tank_tokens']:
            self.tracked_target = chosen[3]
        self.last_decision = {
            'command':chosen[0], 'target':self.target, 'immediate_win':self.is_winning_shot(chosen),
            'expansions':self.expansions, 'planning_truncated':self._expired(),
            'elapsed_ms':round((time.perf_counter()-started)*1000,3),
            'movement_blocked_by_unknown_H_area':self.movement_unknown,
            'confirmed_dead_enemies':sorted(self.dead_enemies),
            'confirmed_dead_allies':sorted(self.dead_allies),
            'supply_observations':list(self.supply_observations),
            'defending':self.defending, 'patrol_status':self.patrol_status,
            'patrol_axis':self.patrol_lane[0] if self.defending and self.patrol_lane else None,
            'patrol_endpoints':[self.patrol_lane[1][0],self.patrol_lane[1][-1]] if self.defending and self.patrol_lane else None,
            'patrol_destination':self.patrol_endpoint if self.defending else None,
            'role':'defender', 'defense_anchor':self.defense_anchor,
            'tracked_target':self.tracked_target, 'movement_radius':self.motion_radius,
        }
        self.recent.append(self.pos)
        if chosen[1] == 'supply':
            self.previous_supply = self.mega,self.rules['supply']['shift']
        return chosen[0]


def receive(sock):
    """Count-framed records WITH final newline. Use only after confirming that boundary."""
    data,expected = bytearray(),None
    while len(data) < MAX_BYTES:
        chunk = sock.recv(4096)
        if not chunk:
            if not data:
                return None
            raise ProtocolError('Connection closed during state')
        data.extend(chunk)
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            if exc.reason == 'unexpected end of data':
                continue
            raise ProtocolError('Invalid UTF-8') from exc
        if '\n' not in text:
            continue
        if expected is None:
            first = text.split('\n',1)[0].strip()
            # Terminal tokens need the same boundary; never accept a prefix of a header.
            if first in ('0','-1') and text.strip() == first:
                return None
            h,w,na,ne,nc = header_values(first)
            expected = 1+h+na+ne+nc
        if text.count('\n') >= expected:
            parse_data(text)
            return text
    raise ProtocolError('State exceeds local size limit')


def wire_command(command, prefix=''):
    if any(ch in command+prefix for ch in ('\r','\n','\x00')):
        raise ProtocolError('Wire command cannot contain line breaks or NUL')
    return (prefix+command+' ').encode('utf-8')


def run(rules, nickname, prefix=''):
    rules = merge_rules(rules)
    transport = rules['transport']
    if transport.get('framing') != 'lines':
        raise ConfigurationError('Live receive boundary is unknown. Confirm final-newline records before setting transport.framing="lines"')
    bot = Bot(rules)
    with socket.create_connection((HOST,PORT),timeout=transport['connect_timeout']) as sock:
        # Waiting for five other clients is not this bot's decision-time budget.
        sock.settimeout(transport.get('read_timeout'))
        sock.sendall(wire_command('INIT '+nickname,prefix))
        while (data := receive(sock)) is not None:
            command = bot.choose(data)
            if not bot.validate(command):
                raise NoLegalAction('Pre-send validation failed')
            sock.sendall(wire_command(command,prefix))


def main():
    parser = argparse.ArgumentParser(description='TeamBattle-only bot; offline replay needs no server')
    parser.add_argument('launcher_prefix',nargs='?',default='',help='Exact optional launcher prefix; no separator is added')
    parser.add_argument('--rules',help='JSON overrides for unresolved settings')
    parser.add_argument('--replay',help='One saved complete state, UTF-8')
    parser.add_argument('--explain',action='store_true',help='Decision details to stderr')
    parser.add_argument('--inspect',action='store_true',help='With --replay, inspect observed fields without choosing an action')
    parser.add_argument('--nickname',default=NICKNAME)
    parser.add_argument('--cipher-pair',nargs=2,metavar=('CIPHER','KNOWN_PLAINTEXT'),help='Calculate a shift from a confirmed plaintext; no connection')
    args = parser.parse_args()
    if args.cipher_pair:
        print(infer_cipher_shift(*args.cipher_pair))
        return
    rules = None
    if args.rules:
        with open(args.rules,encoding='utf-8-sig') as file:
            rules = json.load(file)
    if args.replay:
        bot = Bot(rules)
        with open(args.replay,encoding='utf-8-sig') as file:
            data = file.read()
        if args.inspect:
            bot.load(data)
            print(json.dumps({
                'map_size':[len(bot.grid),len(bot.grid[0])],
                'self':{'id':'M','position':bot.pos,'hp':bot.hp,'facing':bot.info[1],
                        'normal':bot.normal,'mega':bot.mega},
                'allies_hp':bot.ally_hp,'enemies_hp':bot.enemy_hp,
                'H_positions':bot.positions.get('H',[]),
                'cipher_count':len(bot.codes),
                'movement_area_unresolved':bot.movement_unknown,
            },ensure_ascii=False))
            return
        print(bot.choose(data))
        if args.explain:
            print(json.dumps(bot.last_decision,ensure_ascii=False),file=sys.stderr)
    else:
        run(rules,args.nickname,args.launcher_prefix)


if __name__ == '__main__':
    try:
        main()
    except (OSError,ValueError,NoLegalAction) as exc:
        print('[ERROR]',exc,file=sys.stderr)
        sys.exit(1)

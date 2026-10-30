"""배틀싸피 팀전 공격수 v1: 표준 라이브러리만 사용, import 시 접속하지 않음.

매뉴얼 v1.1.10 + 이번 대회 옐로카드 안내를 기준으로 한다.
모서리 H의 안쪽 3x3은 매뉴얼 그림에 근거한 기본 해석이다. 실제 영역이
다르면 --forbidden-cells로 교체한다. 나무 제거 비용/적 위험 비용은 전략
추정치이며 게임 규칙이 아니다. 실제 엔진 호환성과 승률은 별도 검증해야 한다.
"""
import argparse
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
TRANSPARENT = {'G', 'S', 'W'}
ENEMY_TANKS = {'E1', 'E2', 'E3'}
FRIEND_TANKS = {'M1', 'M2', 'M3'}
SHELLS = {'normal': (30, ' F'), 'mega': (70, ' F M')}
MAX_BYTES = 4 * 1024 * 1024
CONFIG = {
    'cipher_shift': None, 'forbidden_cells': None,
    'planning_ms': 40, 'max_expansions': 6000,
    'tree_step_cost': 3.0, 'max_tree_attempts': 6,
}


class ProtocolError(ValueError):
    pass


class NoLegalAction(RuntimeError):
    pass


def header_values(line):
    try:
        fields = list(map(int, line.split()))
        if len(fields) != 5:
            raise ValueError('헤더는 다섯 정수여야 합니다')
        h, w, na, ne, nc = fields
        if h <= 0 or w <= 0 or h*w > 65536 or min(na, ne, nc) < 0 or na+ne+nc > 4096:
            raise ValueError('지도 크기 또는 레코드 수가 잘못되었습니다')
        return h, w, na, ne, nc
    except ValueError as exc:
        raise ProtocolError(str(exc)) from exc


def parse_data(data):
    if not isinstance(data, str) or len(data.encode('utf-8')) > MAX_BYTES:
        raise ProtocolError('입력은 제한 크기 이내의 문자열이어야 합니다')
    lines = data.strip().splitlines()
    if not lines:
        raise ProtocolError('빈 입력입니다')
    h, w, na, ne, nc = header_values(lines[0])
    if len(lines) != 1+h+na+ne+nc:
        raise ProtocolError('헤더와 실제 줄 수가 다릅니다')
    grid = [line.split() for line in lines[1:1+h]]
    if any(len(row) != w for row in grid):
        raise ProtocolError('지도 열 수가 다릅니다')
    def records(rows):
        result = {}
        for row in rows:
            parts = row.split()
            if len(parts) < 2 or parts[0] in result:
                raise ProtocolError('유닛 레코드 누락 또는 중복')
            result[parts[0]] = parts[1:]
        return result
    offset = 1+h
    allies = records(lines[offset:offset+na])
    enemies = records(lines[offset+na:offset+na+ne])
    if set(allies) & set(enemies):
        raise ProtocolError('아군과 적군의 ID가 중복됩니다')
    return grid, allies, enemies, lines[offset+na+ne:]


def decode_cipher(cipher, shift):
    if type(shift) is not int or not 0 <= shift <= 25:
        raise ValueError('암호 이동값은 실제 확인한 0~25 정수여야 합니다')
    if not cipher or any(not 'A' <= ch <= 'Z' for ch in cipher):
        raise ProtocolError('암호문은 영문 대문자 문자열이어야 합니다')
    return ''.join(chr((ord(ch)-65+shift) % 26+65) for ch in cipher)


def infer_cipher_shift(cipher, plaintext):
    shifts = [s for s in range(26) if decode_cipher(cipher, s) == plaintext]
    if len(shifts) != 1:
        raise ValueError('확인된 암호문/평문 쌍에서 이동값을 구할 수 없습니다')
    return shifts[0]


class Bot:
    def __init__(self, config=None):
        self.config = dict(CONFIG)
        if config:
            if set(config)-set(CONFIG):
                raise ValueError('알 수 없는 설정: '+str(set(config)-set(CONFIG)))
            self.config.update(config)
        shift = self.config['cipher_shift']
        if shift is not None:
            decode_cipher('A', shift)
        for key in ('planning_ms', 'tree_step_cost'):
            value = self.config[key]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(key+'는 양의 유한수여야 합니다')
        for key in ('max_expansions', 'max_tree_attempts'):
            if type(self.config[key]) is not int or self.config[key] < 1:
                raise ValueError(key+'는 양의 정수여야 합니다')
        cells = self.config['forbidden_cells']
        if cells is not None and (not isinstance(cells, list) or any(
                not isinstance(p, (list, tuple)) or len(p) != 2 or
                any(type(v) is not int for v in p) for p in cells)):
            raise ValueError('forbidden_cells는 [[행,열], ...] 또는 null입니다')
        self.recent = deque(maxlen=12)
        self.dead_enemies, self.dead_allies = set(), set()
        self.tree_attempts = {}
        self.previous_tree = None
        self.previous_supply = None
        self.supply_failed = False
        self.last_decision = {}
        self.target = None

    def load(self, data):
        self.grid, self.allies, self.enemies, self.codes = parse_data(data)
        self.h, self.w = len(self.grid), len(self.grid[0])
        self.positions = {}
        for r, row in enumerate(self.grid):
            for c, token in enumerate(row):
                self.positions.setdefault(token, []).append((r, c))
        for key in {'M', 'H', 'X'} | FRIEND_TANKS | ENEMY_TANKS:
            if len(self.positions.get(key, [])) > 1:
                raise ProtocolError('중복 유닛 위치: '+key)
        if len(self.positions.get('M', [])) != 1 or 'M' not in self.allies:
            raise ProtocolError('자기 전차 M의 위치/정보가 필요합니다')
        self.pos = self.positions['M'][0]
        try:
            own = self.allies['M']
            if len(own) != 4 or own[1] not in DIRS:
                raise ValueError('M 형식은 HP, 방향, 일반탄, 메가탄입니다')
            self.hp, self.normal, self.mega = int(own[0]), int(own[2]), int(own[3])
            if self.hp <= 0 or self.normal < 0 or not 0 <= self.mega <= 10:
                raise ValueError('자기 HP/잔탄 값이 잘못되었습니다')
            self.enemy_hp = {k: int(v[0]) for k, v in self.enemies.items()}
            self.ally_hp = {k: int(v[0]) for k, v in self.allies.items()}
            if any(len(v) != 1 for k, v in self.allies.items() if k != 'M') or any(len(v) != 1 for v in self.enemies.values()):
                raise ValueError('다른 유닛은 HP만 제공해야 합니다')
            if min(list(self.enemy_hp.values())+list(self.ally_hp.values())) < 0:
                raise ValueError('HP는 음수가 될 수 없습니다')
        except (ValueError, IndexError) as exc:
            raise ProtocolError(str(exc)) from exc
        # 누락 레코드를 사망이라고 추정하지 않는다. HP=0 관측만 누적한다.
        self.dead_enemies.update(k for k in ENEMY_TANKS if self.enemy_hp.get(k) == 0)
        self.dead_allies.update(k for k in FRIEND_TANKS if self.ally_hp.get(k) == 0)
        self.blocked = self._forbidden_area()
        if self.previous_tree is not None and self.inside(self.previous_tree) and self.cell(self.previous_tree) == 'T':
            self.tree_attempts[self.previous_tree] = self.tree_attempts.get(self.previous_tree, 0)+1
        self.previous_tree = None
        self.tree_attempts = {p: n for p, n in self.tree_attempts.items()
                              if self.inside(p) and self.cell(p) == 'T'}
        if self.previous_supply is not None:
            self.supply_failed = self.mega <= self.previous_supply
            self.previous_supply = None

    def _forbidden_area(self):
        explicit = self.config['forbidden_cells']
        if explicit is not None:
            return {tuple(p) for p in explicit}
        blocked = set()
        self.area_interpretation = 'no H'
        for r, c in self.positions.get('H', []):
            if r in (0, self.h-1) and c in (0, self.w-1):
                # 매뉴얼 그림의 모서리 안쪽 3x3 해석. 실제 운영 영역 확인 필요.
                rr = range(min(3, self.h)) if r == 0 else range(max(0, self.h-3), self.h)
                cc = range(min(3, self.w)) if c == 0 else range(max(0, self.w-3), self.w)
                self.area_interpretation = 'corner H: inward 3x3 (diagram inference)'
            else:
                # 비모서리는 H를 포함하는 모든 3x3의 합집합. 보수적 5x5.
                rr, cc = range(max(0, r-2), min(self.h, r+3)), range(max(0, c-2), min(self.w, c+3))
                self.area_interpretation = 'noncorner H: conservative 5x5; override recommended'
            blocked.update((i, j) for i in rr for j in cc)
        return blocked

    def inside(self, p):
        return 0 <= p[0] < self.h and 0 <= p[1] < self.w

    def cell(self, p):
        return self.grid[p[0]][p[1]]

    def tile_damage(self, p):
        return 10 if self.cell(p) == 'S' else 0

    def movable(self, p):
        return self.inside(p) and p not in self.blocked and self.cell(p) in {'G', 'S'}

    def is_target(self, key):
        return key in ENEMY_TANKS | {'X'} and self.enemy_hp.get(key, 0) > 0

    def hit(self, p, direction, vacate_self=False, eliminated=None):
        dr, dc = DIRS[direction]
        for n in range(1, 4):
            q = p[0]+dr*n, p[1]+dc*n
            if not self.inside(q):
                return None
            token = self.cell(q)
            if (vacate_self and q == self.pos) or token == eliminated:
                continue
            if token not in TRANSPARENT:
                return token, q
        return None

    def supply_answer(self):
        shift = self.config['cipher_shift']
        if shift is None or self.supply_failed or self.mega >= 10 or not self.codes:
            return None
        if not any(self.inside((self.pos[0]+dr, self.pos[1]+dc)) and
                   self.cell((self.pos[0]+dr, self.pos[1]+dc)) == 'F' for dr, dc in DIRS.values()):
            return None
        return decode_cipher(self.codes[0], shift)

    def actions(self):
        actions = []
        for direction, (dr, dc) in DIRS.items():
            q = self.pos[0]+dr, self.pos[1]+dc
            if self.movable(q) and self.tile_damage(q) < self.hp:
                actions.append((direction+' A', 'move', q, None, None))
            hit = self.hit(self.pos, direction)
            if hit and (self.is_target(hit[0]) or hit[0] == 'T'):
                for name, stock in [('normal', self.normal), ('mega', self.mega)]:
                    if stock:
                        actions.append((direction+SHELLS[name][1], 'fire', hit[1], hit[0], name))
        answer = self.supply_answer()
        if answer is not None:
            actions.append(('G '+answer, 'supply', self.pos, None, None))
        return actions

    def validate(self, command):
        # 송신 직전 자원/목적지/첫 충돌 대상을 다시 검사한다. S는 허용하지 않는다.
        return any(action[0] == command for action in self.actions())

    def salvo(self, hp):
        choices = []
        for mega in range(min(self.mega, math.ceil(hp/70))+1):
            normal = max(0, math.ceil((hp-70*mega)/30))
            if normal <= self.normal:
                choices.append((normal+mega, mega, normal))
        return min(choices) if choices else None

    def is_winning_shot(self, action):
        return (action[1] == 'fire' and self.is_target(action[3]) and
                self.enemy_hp[action[3]] <= SHELLS[action[4]][0] and
                (action[3] == 'X' or len(self.dead_enemies) >= 1))

    def threats(self, eliminated=None):
        exposed = {}
        for token in ENEMY_TANKS:
            if token == eliminated or self.enemy_hp.get(token, 0) <= 0:
                continue
            for origin in self.positions.get(token, []):
                for dr, dc in DIRS.values():
                    for n in range(1, 4):
                        p = origin[0]+dr*n, origin[1]+dc*n
                        if not self.inside(p):
                            break
                        exposed.setdefault(p, set()).add(token)
                        if p != self.pos and self.cell(p) != eliminated and self.cell(p) not in TRANSPARENT:
                            break
        return exposed

    def danger(self, p, eliminated=None):
        if eliminated not in self.threat_cache:
            self.threat_cache[eliminated] = self.threats(eliminated)
        attackers = self.threat_cache[eliminated].get(p, set())
        hp = self.hp-(self.tile_damage(p) if p != self.pos else 0)
        value = 24*len(attackers)
        # 적 잔탄/행동순서는 미수신. 이 수치는 공격확률이 아닌 전략 위험비용이다.
        if attackers and hp <= 70*len(attackers):
            value += 110 if not self.dead_allies else 350
        return value

    def expired(self):
        return time.perf_counter() >= self.deadline or self.expansions >= self.config['max_expansions']

    def attack_goals(self, target, relaxed):
        goals = {}
        for origin in self.positions.get(target, []):
            for dr, dc in DIRS.values():
                obstruction_count = 0
                for n in range(1, 4):
                    p = origin[0]+dr*n, origin[1]+dc*n
                    if not self.inside(p):
                        break
                    token = self.cell(p)
                    if token == 'M' or (p not in self.blocked and token in {'G', 'S'}):
                        goals[p] = obstruction_count
                    elif relaxed and token == 'T' and p not in self.blocked:
                        goals[p] = obstruction_count
                    if token == 'T':
                        obstruction_count += 1
                    if token != 'M' and token not in TRANSPARENT and not (relaxed and token == 'T'):
                        break
        return goals

    def route(self, goals, relaxed=False):
        """잔여 HP를 넘는 누적 모래 경로 배제. 나무 비용은 추정치일 뿐이다."""
        if not goals:
            return None
        labels = {self.pos: [(0.0, 0, 0)]}
        heap = [(0.0, 0, 0, self.pos, '', 0)]
        while heap and not self.expired():
            cost, loss, tree_count, p, first, steps = heapq.heappop(heap)
            if (cost, loss, tree_count) not in labels[p]:
                continue
            self.expansions += 1
            remaining_trees = goals.get(p, 0) if isinstance(goals, dict) else 0
            if p in goals and (not relaxed or tree_count+remaining_trees <= max(0, self.normal+self.mega-1)):
                return {'cost': cost+remaining_trees*self.config['tree_step_cost'], 'first': first, 'goal': p, 'steps': steps, 'relaxed': relaxed, 'tree_lower_bound': tree_count+remaining_trees}
            for direction, (dr, dc) in DIRS.items():
                q = p[0]+dr, p[1]+dc
                if not self.inside(q) or q in self.blocked:
                    continue
                token = self.cell(q)
                tree = relaxed and token == 'T' and self.normal+self.mega > 0 and self.tree_attempts.get(q, 0) < self.config['max_tree_attempts']
                if token not in {'G', 'S'} and not tree:
                    continue
                count2 = tree_count+int(tree)
                # 나무당 최소 1발이라는 자원 하한. 목표 공격용 1발은 보존한다.
                # 실제 나무의 필요 명중수는 미확인이므로 충분조건은 아니다.
                if count2 > max(0, self.normal+self.mega-1):
                    continue
                loss2 = loss+self.tile_damage(q)
                if loss2 >= self.hp:
                    continue
                edge = (self.config['tree_step_cost'] if tree else 1)+self.tile_damage(q)*0.25+len(self.threat_cache[None].get(q, []))*0.8
                cost2 = cost+edge
                old = labels.setdefault(q, [])
                if any(c <= cost2 and l <= loss2 and t <= count2 for c, l, t in old):
                    continue
                labels[q] = [(c, l, t) for c, l, t in old if not (c >= cost2 and l >= loss2 and t >= count2)]+[(cost2, loss2, count2)]
                if first:
                    first2 = first
                elif tree:
                    first2 = direction+' F' if self.normal else direction+' F M'
                else:
                    first2 = direction+' A'
                heapq.heappush(heap, (cost2, loss2, count2, q, first2, steps+1))
        return None

    def plan(self, target):
        direct = self.route(self.attack_goals(target, False))
        relaxed = None
        if self.normal+self.mega and not self.expired():
            relaxed = self.route(self.attack_goals(target, True), True)
        candidates = []
        for route in (direct, relaxed):
            if route is None:
                continue
            if not route['first']:
                # 가상 사격위치가 현재 칸이면 목표 방향 첫 실제 나무를 제거한다.
                for direction in DIRS:
                    hit = self.hit(self.pos, direction)
                    if hit and hit[0] == 'T':
                        target_pos = self.positions[target][0]
                        dr, dc = DIRS[direction]
                        delta = target_pos[0]-self.pos[0], target_pos[1]-self.pos[1]
                        if ((dr and delta[1] == 0 and delta[0]*dr > 0) or
                                (dc and delta[0] == 0 and delta[1]*dc > 0)):
                            route = dict(route, first=direction+' F' if self.normal else direction+' F M')
                            break
            if route['first'] and self.validate(route['first']):
                candidates.append(route)
        return min(candidates, key=lambda p: p['cost']) if candidates else None

    def score(self, action, planned):
        command, kind, p, key, name = action
        if kind == 'fire' and self.is_target(key):
            hp, damage = self.enemy_hp[key], SHELLS[name][0]
            kill = hp <= damage
            danger = self.danger(self.pos, key if kill else None)
            return ((1000000 if self.is_winning_shot(action) else 0)+
                    min(hp, damage)+80*kill+(65 if key == 'X' else 0)-
                    (12 if name == 'mega' else 0)-danger)
        if kind == 'supply':
            return (100 if self.normal+self.mega == 0 else 32 if self.mega == 0 else -50)-self.danger(self.pos)
        if kind == 'fire':
            # 목적에 기여하는 나무만 높은 점수. 나머지는 마지막 탈출 후보이다.
            base = planned.get(command, -300)
            return base-self.danger(self.pos)-(15 if name == 'mega' else 0)-15*self.tree_attempts.get(p, 0)
        progress = planned.get(command, -65)
        return progress-self.danger(p)-self.tile_damage(p)*1.5-7*self.recent.count(p)

    def choose(self, data):
        started = time.perf_counter()
        self.load(data)
        self.deadline = started+self.config['planning_ms']/1000
        self.expansions = 0
        self.threat_cache = {None: self.threats()}
        actions = self.actions()
        if not actions:
            raise NoLegalAction('유효 행동 없음: 막힘/무탄/미확인 암호/치명적 모래. S로 숨기지 않습니다.')
        winners = [a for a in actions if self.is_winning_shot(a)]
        planned, selected_target = {}, None
        if not winners:
            targets = sorted((k for k in self.enemy_hp if self.is_target(k)),
                             key=lambda k: (k != 'X', self.enemy_hp[k], k))
            best_objective = -math.inf
            for target in targets:
                if self.expired():
                    break
                route = self.plan(target)
                if route:
                    salvo = self.salvo(self.enemy_hp[target])
                    shots = salvo[0] if salvo else 6
                    # 포탑 우선이지만 지나치게 먼 포탑보다 가까운 제거 기회도 고려.
                    value = (75 if target == 'X' else 40)-2.5*route['cost']-2*shots
                    if target == self.target:
                        value += 3
                    if target in ENEMY_TANKS and self.dead_enemies:
                        value += 35
                    planned[route['first']] = max(planned.get(route['first'], -math.inf), value)
                    if value > best_objective:
                        best_objective, selected_target = value, target
            # 무탄이면 확인한 암호를 받을 수 있는 보급소 인접 칸으로 접근한다.
            if self.normal+self.mega <= 1 and self.config['cipher_shift'] is not None and not self.supply_failed and not self.expired():
                supply_goals = {p for r in range(self.h) for c in range(self.w)
                                for p in [(r, c)] if (p == self.pos or self.movable(p)) and
                                any(self.inside((r+dr, c+dc)) and self.cell((r+dr, c+dc)) == 'F' for dr, dc in DIRS.values())}
                route = self.route(supply_goals)
                if route and route['first']:
                    planned[route['first']] = max(planned.get(route['first'], -math.inf),
                        (110 if self.normal+self.mega == 0 else 45)-3*route['cost'])
        chosen = max(winners or actions, key=lambda a: (self.score(a, planned), a[4] == 'normal', a[0]))
        if not self.validate(chosen[0]):
            raise NoLegalAction('송신 직전 검사 실패')
        self.target = selected_target
        self.last_decision = {
            'command': chosen[0], 'target': self.target, 'immediate_win': self.is_winning_shot(chosen),
            'expansions': self.expansions, 'planning_truncated': self.expired(),
            'elapsed_ms': round((time.perf_counter()-started)*1000, 3),
            'forbidden_area': getattr(self, 'area_interpretation', 'explicit cells'),
            'confirmed_dead_enemies': sorted(self.dead_enemies),
            'confirmed_dead_allies': sorted(self.dead_allies),
            'cipher_enabled': self.config['cipher_shift'] is not None and not self.supply_failed,
            'planned_first_actions': planned,
            'legal_tree_fallback': chosen[1] == 'fire' and chosen[3] == 'T' and chosen[0] not in planned,
        }
        self.recent.append(self.pos)
        if chosen[1] == 'supply':
            self.previous_supply = self.mega
        if chosen[1] == 'fire' and chosen[3] == 'T':
            self.previous_tree = chosen[2]
        return chosen[0]


def receive(sock, framing='official'):
    """official은 원본의 단일 recv 호환 방식: TCP 메시지 경계를 보장하지 않는다.

    lines는 마지막 개행까지 보내는 엔진에서만 선택한다. 임의 idle timeout으로
    메시지 끝을 추정하거나, 잘못된 상태에서 명령을 자동 재전송하지 않는다.
    """
    if framing == 'official':
        raw = sock.recv(MAX_BYTES)
        if not raw:
            return None
        text = raw.decode('utf-8')
        if text.strip() in ('0', '-1'):
            return None
        parse_data(text)
        return text
    if framing != 'lines':
        raise ValueError('지원 수신 방식: official, lines')
    data = bytearray()
    expected = None
    while len(data) < MAX_BYTES:
        chunk = sock.recv(4096)
        if not chunk:
            if not data:
                return None
            raise ProtocolError('상태 수신 도중 연결이 닫혔습니다')
        data.extend(chunk)
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            if exc.reason == 'unexpected end of data':
                continue
            raise ProtocolError('UTF-8 입력 오류') from exc
        if '\n' not in text:
            continue
        first = text.split('\n', 1)[0].strip()
        if first in ('0', '-1') and text.strip() == first:
            return None
        if expected is None:
            h, w, na, ne, nc = header_values(first)
            expected = 1+h+na+ne+nc
        if text.count('\n') >= expected:
            parse_data(text)
            return text
    raise ProtocolError('수신 크기 제한 초과')


def wire_command(command, prefix=''):
    if any(ch in command+prefix for ch in ('\r', '\n', '\x00')):
        raise ProtocolError('송신에 개행/NUL을 넣을 수 없습니다')
    return (prefix+command+' ').encode('utf-8')


def run(bot, nickname=NICKNAME, prefix='', host=HOST, port=PORT, framing='official'):
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.settimeout(None)  # 다른 플레이어의 차례 대기시간을 제한하지 않는다.
        sock.sendall(wire_command('INIT '+nickname, prefix))
        while True:
            data = receive(sock, framing)
            if data is None:
                return
            command = bot.choose(data)
            if not bot.validate(command):
                raise NoLegalAction('송신 검사 실패')
            sock.sendall(wire_command(command, prefix))


_default_bot = None


def my_func(game_data):
    """기본코드의 output = my_func(game_data)에 연결할 수 있는 판단 함수."""
    global _default_bot
    if _default_bot is None:
        _default_bot = Bot()
    return _default_bot.choose(game_data)


def main():
    parser = argparse.ArgumentParser(description='배틀싸피 팀전 공격수 후보 v1')
    parser.add_argument('launcher_prefix', nargs='?', default='')
    parser.add_argument('--nickname', default=NICKNAME)
    parser.add_argument('--host', default=HOST)
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--transport', choices=('official', 'lines'), default='official')
    parser.add_argument('--replay', help='UTF-8 전체 수신 상태 파일. 서버 연결 없음')
    parser.add_argument('--explain', action='store_true')
    parser.add_argument('--cipher-shift', type=int, help='현재 경기에서 확인한 복호화 이동값 0~25')
    parser.add_argument('--cipher-pair', nargs=2, metavar=('CIPHER', 'PLAINTEXT'))
    parser.add_argument('--forbidden-cells', help='확인된 전체 금지 좌표 [[행,열],...] JSON 파일')
    args = parser.parse_args()
    if args.cipher_pair:
        print(infer_cipher_shift(*args.cipher_pair))
        return
    config = {'cipher_shift': args.cipher_shift}
    if args.forbidden_cells:
        with open(args.forbidden_cells, encoding='utf-8-sig') as file:
            config['forbidden_cells'] = json.load(file)
    bot = Bot(config)
    if args.replay:
        with open(args.replay, encoding='utf-8-sig') as file:
            print(bot.choose(file.read()))
        if args.explain:
            print(json.dumps(bot.last_decision, ensure_ascii=False), file=sys.stderr)
    else:
        run(bot, args.nickname, args.launcher_prefix, args.host, args.port, args.transport)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, NoLegalAction) as exc:
        print('[ERROR]', exc, file=sys.stderr)
        sys.exit(1)

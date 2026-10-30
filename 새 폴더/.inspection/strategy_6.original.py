# 배틀싸피 팀대항전 최종 전략: 에이스 1 + 수비 2 (쌍 초소·교전 이동·메가 비축)
# 기반: develop.py 통신부·입출력 규약 동일, 표준 라이브러리만 사용
# 3명 모두 이 파일을 그대로 사용 (역할은 첫 턴 위치로 자동 결정)
import socket
import heapq
from collections import deque

HOST = '127.0.0.1'
PORT = 8747

sock = socket.socket()

def init(nickname):
    try:
        print(f'[STATUS] Trying to connect to {HOST}:{PORT}')
        sock.connect((HOST, PORT))
        print('[STATUS] Connected')
        init_command = f'INIT {nickname}' 

        return submit(init_command)

    except Exception as e:
        print('[ERROR] Failed to connect. Please check if Battle SSAFY is waiting for connection.')
        print(e)
        return None

def submit(string_to_send):
    try:
        sock.send((string_to_send + ' ').encode('utf-8'))
        return receive()
        
    except Exception as e:
        print('[ERROR] Failed to connect. Please check if Battle SSAFY is waiting for connection.')

    return None

def receive():
    try:
        game_data = (sock.recv(1024)).decode()
        if int(game_data[0]) > 0:
            return game_data
        close()
    except Exception as e:
        print('[ERROR] Failed to connect. Please check if Battle SSAFY is waiting for connection.')

    return None

def close():
    try:
        if sock is not None: sock.close()
        print('[STATUS] Connection closed')
    
    except Exception as e:
        print('[ERROR] Network connection has been corrupted.')

##############################
# [공통] 게임 규칙 기반 유틸리티 (사용자 매뉴얼 v1.1.10 / 팀배틀 가이드에서 확인된 규칙만 사용)
#  - 지형: G 이동 가능, S 이동 가능(체력 -10), W 이동 불가 / 포탄은 G·S·W 위를 통과
#  - 지물: T 나무(이동 불가, 포탄으로 파괴 가능), R 바위(파괴 불가), F 보급시설(이동·파괴 불가)
#  - 유닛: M 나, M1~M3 아군 탱크, H 아군 포탑, E1~E3 적 탱크, X 적 포탑
#  - 포탄 사거리 3칸, 일반 30 / 메가 70 데미지
#  - 옐로카드: S·방향만 입력, 이동 불가 칸으로 A, 메가 0개에서 F M, 허공/바위/보급시설에 F,
#              아군 포탑 3x3 진입
#  - 암호: 카이사르, 매뉴얼 예시 SRKKCVJJRWP -> BATTLESSAFY (+9 이동)
##############################

DIRS = [(0, 1), (1, 0), (0, -1), (-1, 0)]
DCH = ['R', 'D', 'L', 'U']
FIRE_RANGE = 3
NORMAL_DMG, MEGA_DMG = 30, 70
SAND_COST = 3          # 모래 1칸 = 체력 10 손실 → 100턴 판정(피해량)에도 불리하므로 3턴 비용으로 환산
CIPHER_SHIFT = 9


def to_int(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def is_ground(cell):
    # 'G', 'G1', 'G2'(포탑 주변 구역 표기) 모두 일반 지형으로 취급
    return cell[:1] == 'G' and (len(cell) == 1 or cell[1:].isdigit())


def passthrough(cell):
    # 포탄이 통과하는 칸 (지형)
    return is_ground(cell) or cell in ('S', 'W')


def decode_cipher(text, shift=CIPHER_SHIFT):
    return ''.join(chr((ord(c) - 65 + shift) % 26 + 65) if 'A' <= c <= 'Z' else c for c in text.strip().upper())


class State:
    """한 턴의 입력을 해석한 결과 (매 턴 새로 생성 → 전역 상태 누적 없음)"""

    def __init__(self, game_data):
        rows = game_data.strip('\n').split('\n')
        head = rows[0].split()
        self.H, self.W = to_int(head[0]), to_int(head[1])
        na, ne = to_int(head[2]), to_int(head[3])
        nc = to_int(head[4]) if len(head) > 4 else 0
        self.grid = []
        for i in range(self.H):
            cols = rows[1 + i].split() if 1 + i < len(rows) else []
            cols = (cols + ['R'] * self.W)[:self.W]   # 행이 짧으면 바위로 채워 안전하게 처리
            self.grid.append(cols)
        idx = 1 + self.H
        self.allies, self.enemies = {}, {}
        for _ in range(na):
            if idx < len(rows):
                p = rows[idx].split()
                if p:
                    self.allies[p[0]] = p[1:]
            idx += 1
        for _ in range(ne):
            if idx < len(rows):
                p = rows[idx].split()
                if p:
                    self.enemies[p[0]] = p[1:]
            idx += 1
        self.codes = [rows[i].strip() for i in range(idx, min(idx + nc, len(rows))) if rows[i].strip()]

        me = self.allies.get('M', [])
        self.hp = to_int(me[0], 100) if len(me) > 0 else 100
        self.normal = to_int(me[2], 0) if len(me) > 2 else 0
        self.mega = to_int(me[3], 0) if len(me) > 3 else 0

        self.pos = {}
        for r in range(self.H):
            for c in range(self.W):
                v = self.grid[r][c]
                if v in ('M', 'H', 'X', 'F') or v[:1] in ('M', 'E') and v[1:].isdigit():
                    self.pos.setdefault(v, (r, c))
        self.me = self.pos.get('M')
        self.my_turret = self.pos.get('H')
        self.enemy_turret = self.pos.get('X')
        self.enemy_tanks = {k: v for k, v in self.pos.items() if k[:1] == 'E'}
        self.ally_tanks = {k: v for k, v in self.pos.items() if k[:1] == 'M' and k != 'M'}
        self.zone = set()
        if self.my_turret:
            tr, tc = self.my_turret
            # 포탑이 모서리에 있으므로 '포탑을 포함해 맵 안쪽으로 3x3' (맵의 G1/G2 구역과 동일)
            rs = range(tr - 2, tr + 1) if tr >= self.H // 2 else range(tr, tr + 3)
            cs = range(tc - 2, tc + 1) if tc >= self.W // 2 else range(tc, tc + 3)
            self.zone = {(r, c) for r in rs for c in cs}
            # 포탑이 모서리가 아닐 경우 대비: 중심 3x3도 함께 금지
            self.zone |= {(tr + a, tc + b) for a in (-1, 0, 1) for b in (-1, 0, 1)}

    # ---------- 기본 판정 ----------
    def inside(self, r, c):
        return 0 <= r < self.H and 0 <= c < self.W

    def can_enter(self, r, c):
        if not self.inside(r, c) or (r, c) in self.zone:
            return False
        v = self.grid[r][c]
        return is_ground(v) or v == 'S'

    def enemy_hp(self, name):
        return to_int(self.enemies.get(name, ['100'])[0], 100)

    def first_hit(self, r, c, d):
        """(r,c)에서 d 방향으로 쐈을 때 처음 맞는 대상 (이름, 위치) / 없으면 None"""
        dr, dc = DIRS[d]
        for k in range(1, FIRE_RANGE + 1):
            nr, nc = r + dr * k, c + dc * k
            if not self.inside(nr, nc):
                return None
            v = self.grid[nr][nc]
            if passthrough(v):
                continue
            return v, (nr, nc)
        return None

    def fire_cmd(self, d, use_mega):
        if use_mega and self.mega > 0:
            return DCH[d] + ' F M'
        return DCH[d] + ' F'

    def shots_from(self, r, c):
        """현재 위치에서 쏠 수 있는 유효 대상 목록 [(이름, 방향)] (아군·바위·보급시설·허공 제외)"""
        res = []
        for d in range(4):
            hit = self.first_hit(r, c, d)
            if hit is None:
                continue
            name = hit[0]
            if name == 'X' or name[:1] == 'E' or name == 'T':
                res.append((name, d))
        return res

    def can_shoot_target(self, r, c, target):
        """(r,c)에서 target 좌표를 직선 3칸 이내, 가로막힘 없이 맞힐 수 있는 방향"""
        tr, tc = target
        for d, (dr, dc) in enumerate(DIRS):
            for k in range(1, FIRE_RANGE + 1):
                nr, nc = r + dr * k, c + dc * k
                if not self.inside(nr, nc):
                    break
                if (nr, nc) == (tr, tc):
                    return d
                if not passthrough(self.grid[nr][nc]):
                    break
        return None

    def attack_cells(self, target):
        """target을 쏠 수 있는 칸 집합 (역방향 사선 계산, 맵 전체 탐색보다 저렴)"""
        cells = set()
        if target is None:
            return cells
        tr, tc = target
        for dr, dc in DIRS:
            for k in range(1, FIRE_RANGE + 1):
                r, c = tr + dr * k, tc + dc * k
                if not self.inside(r, c):
                    break
                v = self.grid[r][c]
                if (r, c) == self.me or self.can_enter(r, c):
                    cells.add((r, c))
                if not passthrough(v) and (r, c) != self.me:
                    break
        return cells

    def threat_cells(self):
        """적 탱크가 다음 턴에 쏠 수 있는 칸 (회피용 비용)"""
        th = set()
        for (er, ec) in self.enemy_tanks.values():
            for dr, dc in DIRS:
                for k in range(1, FIRE_RANGE + 1):
                    r, c = er + dr * k, ec + dc * k
                    if not self.inside(r, c):
                        break
                    th.add((r, c))
                    if not passthrough(self.grid[r][c]) and (r, c) != self.me:
                        break
        return th

    # ---------- 경로 탐색 ----------
    def dijkstra(self, goals, extra_cost=None, tree_cost=2):
        """다익스트라: 이동 비용이 지형마다 다름(G=1, S=1+모래, T=사격1+이동1).
        goals에 도달하는 최소 비용 경로의 '첫 행동'과 비용을 반환."""
        if self.me is None or not goals:
            return None, None
        if self.me in goals:
            return 'HERE', 0
        sr, sc = self.me
        dist = {self.me: 0}
        pq = [(0, sr, sc, None)]
        while pq:
            cost, r, c, first = heapq.heappop(pq)
            if cost > dist.get((r, c), 1 << 30):
                continue
            if (r, c) in goals:
                return first, cost
            for d, (dr, dc) in enumerate(DIRS):
                nr, nc = r + dr, c + dc
                if not self.inside(nr, nc) or (nr, nc) in self.zone:
                    continue
                v = self.grid[nr][nc]
                if is_ground(v):
                    step, act = 1, DCH[d] + ' A'
                elif v == 'S':
                    step, act = 1 + SAND_COST, DCH[d] + ' A'
                elif v == 'T' and tree_cost is not None:
                    step, act = tree_cost, DCH[d] + ' F'   # 나무는 쏴서 없앤 뒤 지나감
                else:
                    continue
                if extra_cost:
                    step += extra_cost.get((nr, nc), 0)
                nd = cost + step
                if nd < dist.get((nr, nc), 1 << 30):
                    dist[(nr, nc)] = nd
                    # 첫 칸이 나무면 실제 첫 행동은 '그 방향으로 발사'
                    heapq.heappush(pq, (nd, nr, nc, first if first is not None else act))
        return None, None

    def bfs_dist(self, start, targets):
        """균일 비용 BFS (팀 역할 배정 시 '대략적 거리' 비교용)"""
        if start is None or not targets:
            return 1 << 30
        q = deque([(start, 0)])
        seen = {start}
        while q:
            (r, c), d = q.popleft()
            if (r, c) in targets:
                return d
            for dr, dc in DIRS:
                nr, nc = r + dr, c + dc
                if (nr, nc) in seen or not self.inside(nr, nc):
                    continue
                v = self.grid[nr][nc]
                if is_ground(v) or v in ('S', 'T') or (nr, nc) in targets:
                    if (nr, nc) in self.zone:
                        continue
                    seen.add((nr, nc))
                    q.append(((nr, nc), d + 1))
        return 1 << 30

    def safe_move(self, avoid=None):
        """옐로카드를 피하기 위한 마지막 수단: 들어갈 수 있는 옆 칸으로 이동(위협 칸 회피 우선)"""
        if self.me is None:
            return 'S'
        avoid = avoid or set()
        cand = []
        for d, (dr, dc) in enumerate(DIRS):
            nr, nc = self.me[0] + dr, self.me[1] + dc
            if self.can_enter(nr, nc):
                cand.append(((nr, nc) in avoid, self.grid[nr][nc] == 'S', d))
        if cand:
            cand.sort()
            return DCH[cand[0][2]] + ' A'
        for name, d in self.shots_from(*self.me):
            return self.fire_cmd(d, False)
        return 'S'


##############################
# 전략별 의사결정 함수 (core.State 사용)
##############################


# ============================================================
# 전략 1: 최단 경로 + 목표(적 포탑) 달성 중심  — 다익스트라
#  * 이동 비용이 지형마다 다르므로(G 1, S 체력손실, T 사격+이동 2) BFS가 아닌 다익스트라 사용
#  * 목표 = '적 포탑을 쏠 수 있는 칸 집합' → 다중 목표 1회 탐색(포탑 칸 자체로 가는 것보다 최대 3칸 단축)
#  * 우선순위: 포탑 사격 > 길을 막는 적 탱크 사격 > 경로 이동
# ============================================================
def decide_rush(st):
    if st.me is None:
        return 'S'
    r, c = st.me
    shots = st.shots_from(r, c)
    for name, d in shots:
        if name == 'X':
            return st.fire_cmd(d, True)
    goals = st.attack_cells(st.enemy_turret)
    act, cost = st.dijkstra(goals)
    if act and act != 'HERE':
        # 다음 칸이 적 탱크로 막혀 있으면 그 탱크를 사격
        return act
    # 포탑 경로가 막힘(적 탱크가 길목 점유 등) → 사거리 안 적 탱크 사격
    for name, d in shots:
        if name[:1] == 'E':
            return st.fire_cmd(d, True)
    # 적 탱크를 장애물로 보지 않는 경로(탱크 칸 = 사격 후 통과로 가정)로 재탐색
    tank_goals = set()
    for p in st.enemy_tanks.values():
        tank_goals |= st.attack_cells(p)
    act, _ = st.dijkstra(tank_goals)
    if act and act != 'HERE':
        return act
    return st.safe_move()


# ============================================================
# 전략 2: 전장 상황 평가 함수 중심 — 후보 행동 점수화(그리디 + 다익스트라 거리)
#  평가 항목(근거)
#   - 포탑 사격 1000: 포탑 파괴 = 즉시 승리
#   - 적 탱크 사격 300 + 처치 가능 시 +500: 적 탱크 2대 파괴 = 즉시 승리, 처치하면 위협 제거
#   - 체력이 낮은 적일수록 가산(-hp): 처치까지 남은 사격 수 최소화
#   - 메가 확보(보급시설 인접, 메가 < 2) 250: 포탑 체력 100 → 메가 2발이면 파괴(일반은 4발)
#   - 이동: 포탑 공격 칸까지 다익스트라 비용을 감점, 적 사선(위협 칸)은 +2 비용
#  * 매 턴 재평가하므로 목표가 바뀌어도 왕복이 생기지 않도록 '포탑 접근'이 항상 기본값
# ============================================================
def decide_eval(st):
    if st.me is None:
        return 'S'
    pass
    r, c = st.me
    best = (-10 ** 9, None)

    def consider(score, cmd):
        nonlocal best
        if cmd and score > best[0]:
            best = (score, cmd)

    for name, d in st.shots_from(r, c):
        if name == 'X':
            consider(1000, st.fire_cmd(d, True))
        elif name[:1] == 'E':
            hp = st.enemy_hp(name)
            dmg = MEGA_DMG if st.mega > 0 else NORMAL_DMG
            consider(300 + (500 if dmg >= hp else 0) - hp, st.fire_cmd(d, True))

    # 보급시설 인접 + 암호문 존재 → 메가 포탄 확보
    if st.codes and st.mega < 2:
        consider(250, 'G ' + decode_cipher(st.codes[0]))

    threat = {p: 2 for p in st.threat_cells()}
    goals = st.attack_cells(st.enemy_turret)
    act, cost = st.dijkstra(goals, extra_cost=threat)
    if act and act != 'HERE':
        consider(200 - cost, act)

    # 포탑 접근이 불가하면 가장 약한 적 탱크 쪽으로
    if best[1] is None and st.enemy_tanks:
        weakest = min(st.enemy_tanks, key=lambda k: st.enemy_hp(k))
        act, cost = st.dijkstra(st.attack_cells(st.enemy_tanks[weakest]), extra_cost=threat)
        if act and act != 'HERE':
            consider(100 - cost, act)

    return best[1] or st.safe_move(set(threat))


# ============================================================
# 전략 3: 팀 협력 — 역할 분담(통신 없이, 모두가 보는 동일 정보로 결정)
#  * 팀원 간 통신/저장 기능은 확인되지 않음 → 각 탱크가 '현재 맵의 아군 위치'만으로
#    같은 규칙으로 역할을 계산하므로 서로 다른 결과가 나오지 않는다.
#  * 역할: 포탑까지 가장 가까운 2대 = 공격조, 나머지 1대 = 사냥조(적 탱크 추적)
#    아군이 1대 이하로 줄면 남은 탱크는 공격조.
#  * 공격조 2대는 서로 다른 공격 칸을 목표로 배정(같은 칸 경합으로 길막 방지)
#  * 모든 역할 공통: 포탑이 사선에 있으면 즉시 사격, 적 탱크가 사선에 있으면 사격
# ============================================================
_DECODE_TRIES = [0]


def decide_team(st, hunter_range=None, use_decode=False):
    if st.me is None:
        return 'S'
    r, c = st.me
    shots = st.shots_from(r, c)
    for name, d in shots:
        if name == 'X':
            return st.fire_cmd(d, True)
    # 메가 1발 확보: 메가 70 + 일반 30 = 포탑 100 → 2대가 한 라운드에 파괴 (일반만이면 2라운드)
    if use_decode and st.codes and st.mega == 0 and _DECODE_TRIES[0] < 2:
        _DECODE_TRIES[0] += 1
        pass
        return 'G ' + decode_cipher(st.codes[0])

    goals = st.attack_cells(st.enemy_turret)
    tanks = dict(st.ally_tanks)
    tanks['M'] = st.me
    # 모두가 같은 기준으로 계산: (포탑 공격 칸까지 BFS 거리, 좌표)
    order = sorted(tanks.items(), key=lambda kv: (st.bfs_dist(kv[1], goals), kv[1]))
    names = [k for k, _ in order]
    my_rank = names.index('M')
    role = 'hunter' if (len(names) >= 3 and my_rank == len(names) - 1 and st.enemy_tanks) else 'attacker'
    if role == 'hunter' and hunter_range is not None:
        near = min(abs(p[0] - r) + abs(p[1] - c) for p in st.enemy_tanks.values())
        if near > hunter_range:
            role = 'attacker'

    # 적 탱크 사격은 역할과 관계없이 (처치 가능 or 사냥조)일 때 우선
    pass
    tank_shots = [(st.enemy_hp(n), n, d) for n, d in shots if n[:1] == 'E']
    if tank_shots:
        hp, n, d = min(tank_shots)
        dmg = MEGA_DMG if st.mega > 0 else NORMAL_DMG
        if role == 'hunter' or dmg >= hp or len(names) == 1:
            return st.fire_cmd(d, not use_decode)

    threat = {p: 1 for p in st.threat_cells()}
    if role == 'attacker':
        # 공격조 내 순번에 따라 서로 다른 공격 칸 배정
        attackers = [n for n in names if not (len(names) >= 3 and n == names[-1] and st.enemy_tanks)]
        k = attackers.index('M') if 'M' in attackers else 0
        ranked = sorted(goals, key=lambda p: (abs(p[0] - r) + abs(p[1] - c), p))
        taken = set()
        for other in attackers[:k]:
            op = tanks[other]
            if ranked:
                pick = min((g for g in ranked if g not in taken),
                           key=lambda p: (abs(p[0] - op[0]) + abs(p[1] - op[1]), p), default=None)
                if pick:
                    taken.add(pick)
        mine = [g for g in ranked if g not in taken] or ranked
        act, _ = st.dijkstra(set(mine[:3]), extra_cost=threat)
        if not act or act == 'HERE':
            act, _ = st.dijkstra(goals, extra_cost=threat)
        if act and act != 'HERE':
            return act
    else:
        # 사냥조: 가장 약한 적 탱크를 쏠 수 있는 칸으로
        tgt = min(st.enemy_tanks, key=lambda k2: (st.enemy_hp(k2), k2))
        act, _ = st.dijkstra(st.attack_cells(st.enemy_tanks[tgt]))
        if act and act != 'HERE':
            return act
        act, _ = st.dijkstra(goals)
        if act and act != 'HERE':
            return act

    if tank_shots:
        return st.fire_cmd(min(tank_shots)[2], True)
    return st.safe_move(set(threat))


# ============================================================
# 전략 4: 1 공격 + 2 수비 (후공에서도 이기기 위한 구조)
#  * 포탑 레이스는 선공이 유리 → 수비 2대가 '적이 우리 포탑을 쏠 수 있는 칸(사격 칸)'을
#    미리 사선에 넣고 기다렸다가 먼저 쏜다. 적 탱크 2대 파괴 = 즉시 승리.
#  * 수비 위치: 사격 칸을 가장 많이 사선(3칸, 가로막힘 없음)에 넣는 칸 2곳(겹침 최소화)
#  * 대기 중에는 S(옐로카드) 대신 초소 ↔ 옆 칸 왕복
#  * 표적 우선순위(가장 위협적인 적): ① 지금 우리 포탑을 쏠 수 있는 적 ② 우리 포탑에 가까운 적
#    ③ 체력이 낮아 처치 가능한 적 → 집중 사격으로 빠르게 2대 파괴
#  * 공격 1대: 전략 3 공격조와 동일 + 보급시설 인접 시 메가 1발 확보, 메가는 포탑에만 사용
# ============================================================
_ROLE = {}
GUARD_MEGA = [0]
GUARD_SAFE = [8]
GUARD_F_RANGE = [6]


def _lines_from(st, p, rng=3):
    """p에서 4방향 사선으로 맞힐 수 있는 칸 목록"""
    out = []
    for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
        for k in range(1, rng + 1):
            r, c = p[0] + dr * k, p[1] + dc * k
            if not st.inside(r, c):
                break
            out.append((r, c))
            v = st.grid[r][c]
            pass
            if not passthrough(v) and (r, c) != st.me and v[:1] not in ('M', 'E'):
                break
    return out


def _enemy_fire_cells(st):
    """적 탱크가 서서 우리 포탑(H)을 쏠 수 있는 칸 (우리 3x3 구역 포함, 적은 진입 가능)"""
    pass
    cells = set()
    if not st.my_turret:
        return cells
    for p in _lines_from(st, st.my_turret):
        v = st.grid[p[0]][p[1]]
        if is_ground(v) or v == 'S' or v[:1] in ('E', 'M'):
            cells.add(p)
    return cells


def _guard_posts(st):
    pass
    fire = _enemy_fire_cells(st)
    hr, hc = st.my_turret
    # 적이 사격 칸으로 들어오는 길목(사격 칸 주변 1칸)도 가중치 0.4
    approach = {(r + a, c + b) for (r, c) in fire for a, b in ((0, 1), (1, 0), (0, -1), (-1, 0))} - fire
    cand = []
    for r in range(st.H):
        for c in range(st.W):
            if abs(r - hr) + abs(c - hc) > 7 or (r, c) in st.zone:
                continue
            v = st.grid[r][c]
            if not (is_ground(v) or (r, c) == st.me or v[:1] == 'M'):
                continue
            seen = set(_lines_from(st, (r, c)))
            score = len(seen & fire) + 0.4 * len(seen & approach) - 0.05 * (abs(r - hr) + abs(c - hc))
            cand.append((score, (r, c), seen))
    cand.sort(reverse=True)
    if not cand:
        return []
    first = cand[0]
    best2, b2 = None, -1e9
    for score, p, seen in cand[1:]:
        if p == first[1]:
            continue
        uni = len((seen | first[2]) & fire) + 0.4 * len((seen | first[2]) & approach)
        if uni > b2 + 1e-9:
            b2, best2 = uni, p
    posts = [first[1]] + ([best2] if best2 else [])
    if ALL_GUARD[0] and best2:
        used = set(first[2])
        for score, p, seen in cand:
            if p == best2:
                used |= seen
        b3, best3 = -1e9, None
        for score, p, seen in cand:
            if p in posts or any(abs(p[0] - q[0]) + abs(p[1] - q[1]) < 2 for q in posts):
                continue
            u = seen | used
            val = len(u & fire) + 0.4 * len(u & approach)
            if val > b3 + 1e-9:
                b3, best3 = val, p
        if best3:
            posts.append(best3)
    return posts


ALL_GUARD = [False]


def _threat_key(st, name):
    p = st.enemy_tanks[name]
    on_fire_cell = p in _enemy_fire_cells(st)
    hr, hc = st.my_turret if st.my_turret else p
    return (0 if on_fire_cell else 1, abs(p[0] - hr) + abs(p[1] - hc), st.enemy_hp(name))


def decide_guard(st, slot):
    if st.me is None:
        return 'S'
    r, c = st.me
    shots = st.shots_from(r, c)
    for name, d in shots:
        if name == 'X':
            return st.fire_cmd(d, True)
    tank_shots = [(_threat_key(st, n), d) for n, d in shots if n[:1] == 'E']
    if tank_shots:
        return st.fire_cmd(min(tank_shots)[1], True)   # 메가는 수비에서 적 처치용(70+30=100)
    if not st.my_turret:
        return decide_team(st)
    posts = _guard_posts(st)
    if not posts:
        return st.safe_move()
    post = posts[min(slot, len(posts) - 1)]
    # 적이 아직 멀면(우리 포탑까지 거리 > SAFE) 근처 보급시설에서 메가 비축 (메가70+일반30 = 1라운드 처치)
    hr, hc = st.my_turret
    near = min([abs(p[0] - hr) + abs(p[1] - hc) for p in st.enemy_tanks.values()] or [99])
    want = GUARD_MEGA[0]
    if st.codes and st.mega < (want if near > GUARD_SAFE[0] else 2) and st.mega < 10:
        pass
        return 'G ' + decode_cipher(st.codes[0])
    if want and st.mega < want and near > GUARD_SAFE[0]:
        fs = [p for p, v in ((p, st.grid[p[0]][p[1]]) for p in
              ((r2, c2) for r2 in range(st.H) for c2 in range(st.W))) if v == 'F'
              and abs(p[0] - post[0]) + abs(p[1] - post[1]) <= GUARD_F_RANGE[0]]
        adj = {(f[0] + a, f[1] + b) for f in fs for a, b in ((0, 1), (1, 0), (0, -1), (-1, 0))
               if st.can_enter(f[0] + a, f[1] + b) or (f[0] + a, f[1] + b) == st.me}
        if adj:
            act, _ = st.dijkstra(adj)
            if act and act != 'HERE':
                return act
    # 적이 사선 밖에서 접근 중이면, 가장 위협적인 적을 사선에 넣는 칸 중 초소 근처로 이동
    if (r, c) == post or abs(r - post[0]) + abs(c - post[1]) == 1:
        # 초소 ↔ 옆 칸 왕복 (사격 칸 커버가 가장 좋은 옆 칸)
        fire = _enemy_fire_cells(st)
        best = None
        for d, (dr, dc) in enumerate(((0, 1), (1, 0), (0, -1), (-1, 0))):
            nr, nc = r + dr, c + dc
            if not st.can_enter(nr, nc):
                continue
            if (r, c) != post and (nr, nc) != post:
                continue
            cov = len(set(_lines_from(st, (nr, nc))) & fire)
            key = (-(1 if (nr, nc) == post else 0), -cov, st.grid[nr][nc] == 'S')
            if best is None or key < best[0]:
                best = (key, d)
        if best is None and (r, c) == post:
            for d, (dr, dc) in enumerate(((0, 1), (1, 0), (0, -1), (-1, 0))):
                nr, nc = r + dr, c + dc
                if st.can_enter(nr, nc) and st.grid[nr][nc] != 'S':
                    best = ((0,), d)
                    break
        if best is not None:
            pass
            return DCH[best[1]] + ' A'
        return st.safe_move()
    act, _ = st.dijkstra({post})
    if act and act != 'HERE':
        return act
    return st.safe_move()


ACE_RETURN_FIRE = [False]
ACE_DODGE = [1]


def decide_attack1(st):
    """공격 1대: 포탑 공격 칸으로 최단 이동, 메가 1발 확보(포탑 전용)"""
    if st.me is None:
        return 'S'
    r, c = st.me
    shots = st.shots_from(r, c)
    for name, d in shots:
        if name == 'X':
            return st.fire_cmd(d, True)
    if st.codes and st.mega == 0 and _DECODE_TRIES[0] < 2:
        _DECODE_TRIES[0] += 1
        pass
        return 'G ' + decode_cipher(st.codes[0])
    # 에이스 생존: 사선에 들어온 적 탱크는 먼저 쏜다(사선은 서로 대칭 → 안 쏘면 맞는다)
    if ACE_RETURN_FIRE[0]:
        es = [(st.enemy_hp(n), d) for n, d in shots if n[:1] == 'E']
        if es:
            return st.fire_cmd(min(es)[1], False)
    goals = st.attack_cells(st.enemy_turret)
    threat = {p: ACE_DODGE[0] for p in st.threat_cells()}
    act, _ = st.dijkstra(goals, extra_cost=threat)
    if act and act != 'HERE':
        return act
    for name, d in shots:
        if name[:1] == 'E':
            return st.fire_cmd(d, False)
    return st.safe_move()


def decide_1atk2def(st):
    """역할은 첫 턴의 위치로 한 번만 정한다(모든 탱크가 같은 정보로 같은 결론)."""
    if st.me is None:
        return 'S'
    if 'role' not in _ROLE:
        tanks = dict(st.ally_tanks)
        tanks['M'] = st.me
        goals = st.attack_cells(st.enemy_turret)
        names = sorted(tanks, key=lambda k: (st.bfs_dist(tanks[k], goals), tanks[k]))
        atk = names[0]
        defs = sorted([n for n in names if n != atk],
                      key=lambda k: (abs(tanks[k][0] - (st.my_turret or (0, 0))[0]) + abs(tanks[k][1] - (st.my_turret or (0, 0))[1]), tanks[k]))
        if 'M' == atk:
            _ROLE['role'] = ('atk', 0)
        else:
            _ROLE['role'] = ('def', defs.index('M'))
    role, slot = _ROLE['role']
    # 수비조가 모두 파괴되거나 적 탱크가 없으면 공격 전환
    if role == 'def' and not st.enemy_tanks:
        return decide_attack1(st)
    return decide_attack1(st) if role == 'atk' else decide_guard(st, slot)


# ============================================================
# 전략 5: 에이스 1 + 요격 2 → 적 처치 후 2대 출격 (팀 아이디어 디벨롭)
#  * 에이스: 전략 4 공격조와 동일(최단 경로·나무 사격 전진·메가는 포탑 전용)
#  * 요격조: 적 탱크들이 우리 포탑 사격 칸까지 오는 '예상 경로(행·열)'를 계산해
#            그 경로와 사격 칸을 가장 많이 사선에 넣는 칸에서 대기 → 사거리에 들어오면 처치
#  * 적 탱크를 1대라도 처치하면(시작 때보다 적 탱크 수 감소) 요격조 2대도 공격 출격
#    단, 아직 우리 포탑을 노리는 적이 사격 칸에 있으면 그 적부터 처치
# ============================================================
def _enemy_paths(st):
    """각 적 탱크 → 우리 포탑 사격 칸까지 BFS 최단 경로 칸들 (요격 위치 계산용)"""
    from collections import deque as _dq
    pass
    fire = _enemy_fire_cells(st)
    cells = {}
    for name, start in st.enemy_tanks.items():
        prev = {start: None}
        q = _dq([start])
        end = None
        while q:
            p = q.popleft()
            if p in fire:
                end = p
                break
            for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                n = (p[0] + dr, p[1] + dc)
                if n in prev or not st.inside(*n):
                    continue
                v = st.grid[n[0]][n[1]]
                if is_ground(v) or v in ('S', 'T') or n in fire:
                    prev[n] = p
                    q.append(n)
        while end is not None:
            cells[end] = cells.get(end, 0) + 1
            end = prev[end]
    return cells


def _intercept_posts(st):
    pass
    fire = _enemy_fire_cells(st)
    path = _enemy_paths(st)
    hr, hc = st.my_turret
    cand = []
    for r in range(st.H):
        for c in range(st.W):
            if abs(r - hr) + abs(c - hc) > 9 or (r, c) in st.zone:
                continue
            v = st.grid[r][c]
            if not (is_ground(v) or (r, c) == st.me or v[:1] == 'M'):
                continue
            seen = set(_lines_from(st, (r, c)))
            score = len(seen & fire) + 0.5 * sum(path.get(p, 0) for p in seen) - 0.05 * (abs(r - hr) + abs(c - hc))
            cand.append((score, (r, c), seen))
    cand.sort(reverse=True)
    if not cand:
        return []
    first = cand[0]
    best2, b2 = None, -1e9
    for score, p, seen in cand[1:]:
        u = seen | first[2]
        val = len(u & fire) + 0.5 * sum(path.get(q, 0) for q in u)
        if val > b2 + 1e-9:
            b2, best2 = val, p
    return [first[1]] + ([best2] if best2 else [])


def decide_ace(st, intercept=True, sortie=True):
    if st.me is None:
        return 'S'
    if 'role' not in _ROLE:
        tanks = dict(st.ally_tanks)
        tanks['M'] = st.me
        goals = st.attack_cells(st.enemy_turret)
        names = sorted(tanks, key=lambda k: (st.bfs_dist(tanks[k], goals), tanks[k]))
        atk = names[0]
        h = st.my_turret or (0, 0)
        defs = sorted([n for n in names if n != atk], key=lambda k: (abs(tanks[k][0] - h[0]) + abs(tanks[k][1] - h[1]), tanks[k]))
        _ROLE['role'] = ('atk', 0) if atk == 'M' else ('def', defs.index('M'))
        if ALL_GUARD[0]:
            alld = sorted(names, key=lambda k: (abs(tanks[k][0] - h[0]) + abs(tanks[k][1] - h[1]), tanks[k]))
            _ROLE['role'] = ('def', alld.index('M'))
        _ROLE['n0'] = len(st.enemy_tanks)
        if intercept and st.my_turret:
            _ROLE['posts'] = _intercept_posts(st)   # 첫 턴(적 출발 위치 기준)에 한 번만 계산
    role, slot = _ROLE['role']
    if role == 'atk':
        return decide_attack1(st)
    # 출격 조건: 적 탱크를 1대 이상 처치했거나 적 탱크가 없음
    killed = len(st.enemy_tanks) < _ROLE.get('n0', 3)
    if sortie and (killed or not st.enemy_tanks):
        fire = _enemy_fire_cells(st)
        r, c = st.me
        for n, d in st.shots_from(r, c):
            if n[:1] == 'E' and st.enemy_tanks.get(n) in fire:
                return st.fire_cmd(d, True)
        return decide_attack1(st)
    if intercept and _ROLE.get('posts'):
        saved = _guard_posts
        posts = _ROLE['posts']
        globals()['_guard_posts'] = lambda s: posts
        try:
            return decide_guard(st, slot)
        finally:
            globals()['_guard_posts'] = saved
    return decide_guard(st, slot)


# ============================================================
# 전략 6: 전략 4 + 수비 개선
#  (1) 수비 '쌍(pair) 초소': 왕복하는 두 칸 모두가 사격 칸·접근로를 사선에 두도록 선택
#      (기존: 한 칸만 좋고 나머지 칸은 엉뚱한 줄을 봐서 사격 기회 절반 손실)
#  (2) 교전 이동: 적이 가까우면(우리 포탑까지 ENGAGE 이하) 다음 턴에 적을 사선에 넣는 칸으로 이동
# ============================================================
ENGAGE = [5]
G2_MEGA = [2]   # 수비가 비축할 메가 수
G2_SAFE = [10]  # 적이 우리 포탑에서 이 거리보다 멀 때만 비축
G2_FR = [9]     # 초소에서 이 거리 안의 보급시설만 사용


def _cov(st, p, fire, approach):
    seen = set(_lines_from(st, p))
    return len(seen & fire) + 0.4 * len(seen & approach), seen


def _guard_pairs(st):
    pass
    fire = _enemy_fire_cells(st)
    approach = {(r + a, c + b) for (r, c) in fire for a, b in ((0, 1), (1, 0), (0, -1), (-1, 0))} - fire
    hr, hc = st.my_turret
    ok = lambda r, c: st.inside(r, c) and (r, c) not in st.zone and abs(r - hr) + abs(c - hc) <= 7 and \
        (is_ground(st.grid[r][c]) or (r, c) == st.me or st.grid[r][c][:1] == 'M')
    cells = [(r, c) for r in range(st.H) for c in range(st.W) if ok(r, c)]
    cov = {p: _cov(st, p, fire, approach) for p in cells}
    pairs = []
    for p in cells:
        for a, b in ((0, 1), (1, 0)):
            q = (p[0] + a, p[1] + b)
            if q in cov:
                sp, seen_p = cov[p]; sq, seen_q = cov[q]
                pairs.append((min(sp, sq) * 2 + 0.5 * (sp + sq), p, q, seen_p | seen_q))
    pairs.sort(reverse=True)
    if not pairs:
        return []
    first = pairs[0]
    best, bv = None, -1e9
    for v, p, q, seen in pairs:
        if {p, q} & {first[1], first[2]}:
            continue
        u = seen | first[3]
        val = len(u & fire) + 0.4 * len(u & approach) + 0.3 * v
        if val > bv:
            bv, best = val, (v, p, q, seen)
    out = [(first[1], first[2])]
    if best:
        out.append((best[1], best[2]))
    return out


def decide_guard2(st, slot):
    pass
    if st.me is None:
        return 'S'
    r, c = st.me
    shots = st.shots_from(r, c)
    for name, d in shots:
        if name == 'X':
            return st.fire_cmd(d, True)
    tank_shots = [(_threat_key(st, n), d) for n, d in shots if n[:1] == 'E']
    if tank_shots:
        return st.fire_cmd(min(tank_shots)[1], True)
    if st.codes and st.mega < 2:
        pass
        return 'G ' + decode_cipher(st.codes[0])
    if not st.my_turret:
        return decide_team(st)
    if 'pairs' not in _ROLE:
        _ROLE['pairs'] = _guard_pairs(st)
    pairs = _ROLE['pairs']
    if not pairs:
        return st.safe_move()
    p, q = pairs[min(slot, len(pairs) - 1)]
    hr, hc = st.my_turret
    # 메가 비축: 적이 멀 때(포탑까지 > G2_SAFE) 초소 근처 보급시설에서 메가 확보
    far = min([abs(e[0] - hr) + abs(e[1] - hc) for e in st.enemy_tanks.values()] or [99]) > G2_SAFE[0]
    if G2_MEGA[0] and far and st.mega < G2_MEGA[0]:
        if st.codes:
            pass
            return 'G ' + decode_cipher(st.codes[0])
        fs = [(r2, c2) for r2 in range(st.H) for c2 in range(st.W) if st.grid[r2][c2] == 'F'
              and abs(r2 - p[0]) + abs(c2 - p[1]) <= G2_FR[0]]
        adj = {(f[0] + a, f[1] + b) for f in fs for a, b in ((0, 1), (1, 0), (0, -1), (-1, 0))
               if st.can_enter(f[0] + a, f[1] + b)}
        if adj:
            act, _ = st.dijkstra(adj)
            if act and act != 'HERE':
                return act
    # (2) 교전 이동: 가까운 적을 다음 턴 사선에 넣는 옆 칸
    near = [e for e in st.enemy_tanks.values() if abs(e[0] - hr) + abs(e[1] - hc) <= ENGAGE[0]]
    if near and (r, c) in (p, q):
        best = None
        for d, (dr, dc) in enumerate(((0, 1), (1, 0), (0, -1), (-1, 0))):
            nr, nc = r + dr, c + dc
            if not st.can_enter(nr, nc) or abs(nr - p[0]) + abs(nc - p[1]) > 2:
                continue
            seen = set(_lines_from(st, (nr, nc)))
            hits = sum(1 for e in near if e in seen)
            key = (-hits, 0 if (nr, nc) in (p, q) else 1, st.grid[nr][nc] == 'S')
            if best is None or key < best[0]:
                best = (key, d)
        if best is not None and best[0][0] < 0:
            return DCH[best[1]] + ' A'
    if (r, c) == p and st.can_enter(*q):
        return DCH[[(q[0] - r, q[1] - c) == v for v in ((0, 1), (1, 0), (0, -1), (-1, 0))].index(True)] + ' A'
    if (r, c) == q and st.can_enter(*p):
        return DCH[[(p[0] - r, p[1] - c) == v for v in ((0, 1), (1, 0), (0, -1), (-1, 0))].index(True)] + ' A'
    act, _ = st.dijkstra({p, q})
    if act and act != 'HERE':
        return act
    return st.safe_move()


def decide_s6(st):
    if st.me is None:
        return 'S'
    if 'role' not in _ROLE:
        tanks = dict(st.ally_tanks)
        tanks['M'] = st.me
        goals = st.attack_cells(st.enemy_turret)
        names = sorted(tanks, key=lambda k: (st.bfs_dist(tanks[k], goals), tanks[k]))
        atk = names[0]
        h = st.my_turret or (0, 0)
        defs = sorted([n for n in names if n != atk], key=lambda k: (abs(tanks[k][0] - h[0]) + abs(tanks[k][1] - h[1]), tanks[k]))
        _ROLE['role'] = ('atk', 0) if atk == 'M' else ('def', defs.index('M'))
    role, slot = _ROLE['role']
    if role == 'atk' or not st.enemy_tanks:
        return decide_attack1(st)
    return decide_guard2(st, slot)

##############################
# 메인: develop.py와 동일한 통신 구조 (INIT → 데이터 수신 → 명령 전송 반복)
##############################
def my_func(game_data):
    try:
        cmd = decide_s6(State(game_data))
        return cmd if cmd else 'S'
    except Exception as e:
        # 런타임 오류로 연결이 끊기면 팀 전체 패배 → 어떤 경우에도 명령을 보냄
        print('[ERROR] decide failed:', e)
        try:
            return State(game_data).safe_move()
        except Exception:
            return 'S'


NICKNAME = '서울6_박수빈'   # 지역반_이름 (12자 이내)
game_data = init(NICKNAME)

while game_data is not None:
    print(f'{game_data}\n')
    output = my_func(game_data)
    print('[CMD]', output)
    game_data = submit(output)

close()

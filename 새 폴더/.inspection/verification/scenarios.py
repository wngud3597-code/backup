"""Requirement-driven fixtures for the independent, static-opponent model."""
from model import Model
import random
import json
from pathlib import Path


def blank(h, w):
    return [['G']*w for _ in range(h)]


def open_map(size=10, mirror=False, team=False):
    rows = blank(size, size)
    h, x, m = ((0, 0), (size-1, size-1), (3, 0))
    if mirror:
        h, x, m = ((size-1, size-1), (0, 0), (size-4, size-1))
    rows[h[0]][h[1]], rows[x[0]][x[1]], rows[m[0]][m[1]] = 'H', 'X', 'M'
    if team:
        if mirror:
            rows[size-4][size-2], rows[size-2][size-4] = 'M1', 'M2'
        else:
            rows[3][1], rows[1][3] = 'M1', 'M2'
    rs = range(0, 3) if not mirror else range(size-3, size)
    cs = range(0, 3) if not mirror else range(size-3, size)
    return Model(rows, normal=12, mega=5, forbidden={(r,c) for r in rs for c in cs})


def obstacle_detour(size=13, mirror=False):
    model = open_map(size, mirror=mirror, team=True)
    # The barrier has two gaps; it cannot be crossed or destroyed with shells.
    for r in range(1, size-1):
        if r not in (3, size-4):
            model.rows[r][size//2] = 'R'
    for c in range(3, size-2):
        if c != size//2:
            model.rows[size//2][c] = 'W'
    return model


def sand_detour():
    rows = blank(11, 11)
    rows[0][0], rows[10][10], rows[3][0] = 'H', 'X', 'M'
    for r in range(3, 10):
        for c in range(2, 9):
            rows[r][c] = 'S'
    return Model(rows, hp=40, normal=10, mega=5,
                 forbidden={(r,c) for r in range(3) for c in range(3)})


def blocked_shot(blocker='R'):
    rows = blank(7, 7)
    rows[3][1], rows[3][2], rows[3][4] = 'M', blocker, 'X'
    return Model(rows, normal=10, mega=5)


def trapped():
    rows = [['R']*5 for _ in range(5)]
    rows[2][2], rows[4][4] = 'M', 'X'
    return Model(rows, normal=0, mega=0)


def water_shot():
    rows = blank(7, 7)
    rows[3][1], rows[3][2], rows[3][3], rows[3][4] = 'M', 'W', 'S', 'X'
    return Model(rows, normal=0, mega=2)


def mandatory_tree():
    rows = [['R']*9 for _ in range(7)]
    for c in range(1, 8):
        rows[3][c] = 'G'
    rows[3][1], rows[3][3], rows[3][7] = 'M', 'T', 'X'
    return Model(rows, normal=2, mega=1)


def visible_enemy(distance=3, hp=30):
    model = open_map(10)
    model.rows[3][distance] = 'E1'
    model.positions['E1'] = (3, distance)
    model.entity_hp['E1'] = hp
    return model


def empty_ammo_supply():
    rows = blank(9, 9)
    rows[4][1], rows[4][2], rows[4][7] = 'M', 'F', 'X'
    return Model(rows, normal=0, mega=0, codes=['ATTACK'])


def seeded_obstacles(seed, size=16):
    """A reproducible terrain map with a guaranteed ground route to X."""
    rng = random.Random(seed)
    model = open_map(size, team=True)
    reserved = set(model.positions.values()) | model.forbidden
    # Keep a ground path down the left edge and across the bottom edge.
    reserved.update((r, 0) for r in range(3, size))
    reserved.update((size-1, c) for c in range(size))
    for r in range(size):
        for c in range(size):
            if (r,c) not in reserved:
                choice = rng.random()
                model.rows[r][c] = 'R' if choice < .2 else 'W' if choice < .3 else 'S' if choice < .4 else 'G'
    return model


def engine_battle_map(map_index, team='A', own_slot=1):
    """Distributed battle terrain, static opponents, representative valid spawns.

    Engine spawn boxes contain multiple positions. This chooses their center
    rows and column zero for A (mirrored for B); it is not an engine replay.
    """
    source = Path(__file__).resolve().parents[1]/'engine'/'maps'/'all_maps.json'
    all_maps = json.loads(source.read_text(encoding='utf-8-sig'))
    terrain = all_maps[f'stage0_map{map_index}']
    own_home = 'G1' if team == 'A' else 'G2'
    own_turret = 'XA' if team == 'A' else 'XB'
    forbidden = {(r,c) for r,row in enumerate(terrain) for c,token in enumerate(row)
                 if token == own_home or token == own_turret}
    rows = [[('H' if token == own_turret else 'X') if token in {'XA','XB'}
             else 'G' if token in {'G1','G2'} else token for token in row]
            for row in terrain]
    a_spawns = {1:(10,0), 2:(7,0), 3:(4,0)}
    for slot,p in a_spawns.items():
        own_p = p if team == 'A' else (15-p[0],15-p[1])
        enemy_p = (15-p[0],15-p[1]) if team == 'A' else p
        rows[own_p[0]][own_p[1]] = 'M' if slot == own_slot else f'M{slot}'
        rows[enemy_p[0]][enemy_p[1]] = f'E{slot}'
    return Model(rows, hp=100, normal=99, mega=0,
                 forbidden=forbidden, codes=['ATTACK'])


def all_attack_scenarios():
    return {
        'single_10': open_map(10),
        'single_20': open_map(20),
        'single_20_mirrored': open_map(20, mirror=True),
        'team_13': open_map(13, team=True),
        'team_13_mirrored': open_map(13, mirror=True, team=True),
        'rocks_water_13': obstacle_detour(),
        'rocks_water_13_mirrored': obstacle_detour(mirror=True),
        'sand_low_hp': sand_detour(),
        'rock_blocks_X': blocked_shot('R'),
        'ally_blocks_X': blocked_shot('M1'),
        'home_blocks_X': blocked_shot('H'),
        'water_transmits_shell': water_shot(),
        'mandatory_tree': mandatory_tree(),
        'empty_ammo_supply': empty_ammo_supply(),
    }

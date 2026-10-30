"""Offline comparison; never import/execute strategy_6.py's socket/main code.

Only definitions and literal constants are compiled from the supplied file.
This uses the independent static-opponent model, not Unity or a win-rate test.
"""
import ast
import copy
import heapq
import json
from collections import deque
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import attack_bot
from model import Model, run
from scenarios import blank, engine_battle_map, trapped, visible_enemy

SOURCE = HERE.parent/'strategy_6.original.py'


def load_strategy6():
    """Safe top-level selection: no socket creation, init, loop, close or IO."""
    original = ast.parse(SOURCE.read_text(encoding='utf-8-sig'), filename=str(SOURCE))
    selected = []
    excluded_functions = {'init','submit','receive','close','my_func'}
    for node in original.body:
        if isinstance(node, (ast.FunctionDef,ast.ClassDef)):
            if node.name not in excluded_functions:
                selected.append(node)
        elif isinstance(node,ast.Assign):
            try:
                ast.literal_eval(node.value)
            except (ValueError,TypeError):
                continue
            selected.append(node)
    namespace = {'__name__':'strategy6_pure', 'heapq':heapq, 'deque':deque}
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(SOURCE),'exec'),namespace)
    assert 'sock' not in namespace and 'game_data' not in namespace
    return namespace


class Strategy6Attacker:
    def __init__(self):
        self.namespace = load_strategy6()

    def choose(self,state):
        return self.namespace['decide_attack1'](self.namespace['State'](state))


def result(bot, model, limit=100):
    try:
        run(bot,model,max_turns=limit)
        error = None
    except Exception as exc:
        error = type(exc).__name__+': '+str(exc)
    return {
        'X_destroyed':model.turret_destroyed, 'turns':model.turns, 'HP':model.hp,
        'normal':model.normal, 'mega':model.mega,
        'friendly_shots':model.friendly_shots, 'rock_shots':model.rock_shots,
        'empty_ammo_shots':model.no_ammo_shots,
        'forbidden_moves':model.forbidden_moves, 'illegal_moves':model.illegal_moves,
        'supply_failures':model.supply_failures,
        'waits':model.commands.count('S'), 'error':error,
    }


def one_step(model):
    results = {}
    for name, bot in [('strategy6',Strategy6Attacker()),('attack_bot',attack_bot.Bot())]:
        trial = copy.deepcopy(model)
        command = bot.choose(trial.state())
        trial.apply(command)
        results[name] = {'command':command,'HP':trial.hp,'normal':trial.normal,
                         'mega':trial.mega,'empty_ammo_shots':trial.no_ammo_shots}
        if hasattr(bot,'last_decision'):
            results[name]['reason'] = bot.last_decision['reason']
    return results


def low_hp_turret():
    rows = blank(9,9)
    rows[4][1],rows[4][4] = 'M','X'
    return Model(rows,normal=5,mega=1,entity_hp={'X':30})


def zero_ammo_visible_turret():
    model = low_hp_turret()
    model.normal = model.mega = 0
    return model


def lethal_sand_with_safe_detour():
    rows = [['R']*13 for _ in range(13)]
    for r in range(1,11):
        rows[r][1] = rows[r][8] = 'G'
    for c in range(1,9):
        rows[1][c] = rows[10][c] = 'G'
    for c in range(2,7):
        rows[10][c] = 'S'
    rows[10][1],rows[10][8] = 'M','X'
    return Model(rows,hp=30,normal=20,mega=0)


def role_view(positions,own_slot,corridor=False):
    if corridor:
        rows = [['R']*11 for _ in range(11)]
        for r in range(3,8):
            rows[r][0] = rows[r][1] = 'G'
        for c in range(11):
            rows[7][c] = 'G'
        for r in range(8):
            rows[r][10] = 'G'
    else:
        rows = blank(11,11)
    rows[10][0],rows[0][10],rows[10][10] = 'H','X','E1'
    for slot,p in positions.items():
        rows[p[0]][p[1]] = 'M' if slot == own_slot else f'M{slot}'
    return Model(rows,normal=99,mega=0)


def role_decision(model):
    ns = load_strategy6()
    st = ns['State'](model.state())
    goals = st.attack_cells(st.enemy_turret)
    ns['decide_s6'](st)
    return {'role':list(ns['_ROLE']['role']),
            'BFS_self':st.bfs_dist(st.me,goals),
            'home_distance':abs(st.me[0]-st.my_turret[0])+abs(st.me[1]-st.my_turret[1])}


def main():
    terrain = []
    for map_index in range(4):
        for team in ('A','B'):
            for slot in (1,2,3):
                row = {'map':map_index,'team':team,'slot':slot}
                row['strategy6'] = result(Strategy6Attacker(),engine_battle_map(map_index,team,slot))
                row['attack_bot'] = result(attack_bot.Bot(),engine_battle_map(map_index,team,slot))
                terrain.append(row)

    diagnostics = {}
    for distance in (2,3,4,5):
        diagnostics[f'enemy_distance_{distance}'] = one_step(visible_enemy(distance,hp=30))
    diagnostics['X_HP30_mega_conservation'] = one_step(low_hp_turret())
    diagnostics['no_ammo_visible_X'] = one_step(zero_ammo_visible_turret())
    diagnostics['boxed_in_no_ammo'] = one_step(trapped())
    diagnostics['sand_HP30_safe_detour_exists'] = {
        'strategy6':result(Strategy6Attacker(),lethal_sand_with_safe_detour()),
        'attack_bot':result(attack_bot.Bot(),lethal_sand_with_safe_detour()),
    }

    frozen_roles = []
    for map_index in range(4):
        for team in ('A','B'):
            frozen_roles.append({'map':map_index,'team':team,
                'roles':{str(slot):role_decision(engine_battle_map(map_index,team,slot))
                         for slot in (1,2,3)}})

    # Same physical snapshot, different player-relative M. Both in-range tanks
    # are treated as attack_cells(...)=0 from their own view, while allied
    # occupied cells are excluded from the other player's attack-cell set.
    close_positions = {1:(0,7),2:(3,10),3:(6,0)}
    relative_role_counterexample = {
        str(slot):role_decision(role_view(close_positions,slot)) for slot in (1,2,3)}
    # A home-distance assignment and an obstacle-sensitive BFS assignment have
    # different objectives; this corridor makes the closest-home unit the ace.
    corridor_positions = {1:(7,0),2:(6,0),3:(3,0)}
    home_rule_counterexample = {
        str(slot):role_decision(role_view(corridor_positions,slot,corridor=True)) for slot in (1,2,3)}

    lines = [
        'strategy_6.py vs attack_bot.py — offline comparison',
        'Source: .inspection/strategy_6.original.py. AST loads only functions/classes/literal constants.',
        'No original socket construction, INIT, main loop, or close is executed.',
        'Model: distributed battle terrain, static opponents, HP100/normal99/mega0, 100-action limit.',
        'This is not Unity execution or a multiplayer win-rate measurement.',
        'Attack comparison uses decide_attack1 directly; full decide_s6 role selection is reported separately.',
        'Terrain summary: '+json.dumps({
            name:{'X_destroyed':sum(row[name]['X_destroyed'] for row in terrain),
                  'cases':len(terrain),
                  'total_actions':sum(row[name]['turns'] for row in terrain)}
            for name in ('strategy6','attack_bot')},ensure_ascii=False),
        '',
        '24 terrain cases:',
    ]
    for row in terrain:
        lines.append(json.dumps(row,ensure_ascii=False))
    lines += ['', 'Focused decision/resource/sand cases:']
    for name,data in diagnostics.items():
        lines.append(name+' '+json.dumps(data,ensure_ascii=False))
    lines += ['', 'Full strategy6 roles from synchronized representative battle starts:']
    lines.extend(json.dumps(row,ensure_ascii=False) for row in frozen_roles)
    lines += ['', 'Same-snapshot player-relative M counterexample (two initial firing positions):',
              json.dumps(relative_role_counterexample,ensure_ascii=False),
              'Home-distance policy vs BFS counterexample (obstacle corridor):',
              json.dumps(home_rule_counterexample,ensure_ascii=False),
              '',
              'Source evidence:',
              'strategy6 lines 658/676: ACE_RETURN_FIRE defaults False, so visible tanks are skipped while an X route exists.',
              'strategy6 lines 178-181: fire_cmd falls back to a normal shot without checking normal stock.',
              'strategy6 lines 668-670: all visible X use mega if present, including X HP<=30.',
              'strategy6 lines 242-277/302-317: sand has path cost but no cumulative HP survival constraint.',
              'strategy6 lines 671-674: at most two lifetime decode attempts for the attacker.',
              'strategy6 lines 209-225/939-946: attack cells include self M but exclude allied occupied cells; role selection can disagree.',
              'strategy6 lines 941-946: attacker is shortest BFS-to-X, not explicitly the tank farthest from home.',
              'strategy6 lines 39/969-977: direct import connects; recv(1024) and the launcher-prefix omission need integration repair.',
              'strategy6 lines 39: recv(1024) assumes a full state arrives in one TCP read; even smaller states can be fragmented.',
              'state_byte_length='+str(len(engine_battle_map(0,'A',1).state().encode('utf-8'))),
              'Role IDs alone do not always cause disagreement: synchronized standard starts can agree because coordinate tie-breaks are stable.',
              'Freezing roles from different first-turn snapshots adds another possible source of role disagreement.',
    ]
    report = '\n'.join(lines)+'\n'
    destination = HERE/'strategy6_comparison.txt'
    destination.write_text(report,encoding='utf-8')
    print(report)


if __name__ == '__main__':
    main()

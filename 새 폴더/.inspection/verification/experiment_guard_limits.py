"""Small ablation in the independent model; never evidence of real win rates."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT), str(HERE)]
import attack_bot
from compare_teams import OriginalTeam
from team_world import World, play

base = (HERE.parent / "team_logic.pyfrag").read_text(encoding="utf-8")
successor_old = '            self.role = "attack" if self.unit_index == max(live_ids) else "defend" + str(self.unit_index)'
successor_new = '''            intruders = any(self.enemy_hp.get(key, 0) > 0 and
                            any(self.distance(p, home) <= 10 for p in self.positions.get(key, []))
                            for key in ENEMY_TANKS)
            successor = self.unit_index == max(live_ids)
            self.role = ("attack" if successor and
                         (self.assigned_role == "attack" or not intruders)
                         else "defend" + str(self.unit_index))'''


def variant(delay, wide, narrow=False):
    source = base
    if delay:
        assert successor_old in source
        source = source.replace(successor_old, successor_new)
    if wide:
        source = source.replace('def _guard_route(self, goals, home, reserved=()):',
                                'def _guard_route(self, goals, home, reserved=(), radius=None):')
        source = source.replace('        goals = {p for p in goals',
                                '        radius = max(10, self.distance(self.pos, home)) if radius is None else radius\n        goals = {p for p in goals')
        source = source.replace('self.distance(q, home) > 10):', 'self.distance(q, home) > radius):')
        source = source.replace('if self.distance(f, home) > 10 or (pair and min(self.distance(f, p) for p in pair) > 6):',
                                'if self.distance(f, home) > 16 or (pair and min(self.distance(f, p) for p in pair) > 9):')
        source = source.replace('self._guard_route(supply_goals, home, reserved)',
                                'self._guard_route(supply_goals, home, reserved, radius=16)')
        source = source.replace('self.distance(q, home) <= 10:',
                                'self.distance(q, home) <= max(10, self.distance(self.pos, home)):')
    if narrow:
        source = source.replace('if near <= 10 and (self.normal or self.mega):',
                                'if near <= 5 and self.pos in pair and (self.normal or self.mega):')
        source = source.replace('for p in pair) > 3)):', 'for p in pair) > 2)):')
    return source


for name, delay, wide, narrow in [('delay', True, False, False),
                                   ('wide', False, True, False),
                                   ('both', True, True, False),
                                   ('both_original_intercept', True, True, True)]:
    source = variant(delay, wide, narrow)
    namespace = vars(attack_bot).copy()
    exec(compile(source, name, 'exec'), namespace)
    team = namespace['TeamBot']
    results = []
    for map_index in range(4):
        for side in ('A', 'B'):
            for first in ('A', 'B'):
                world = World(map_index, 0)
                bots = {key: team() if key[0] == side else OriginalTeam() for key in world.units}
                outcome = play(world, bots, first=first)
                results.append(dict(map=map_index, side=side, first=first, outcome=outcome,
                                    metrics=world.metrics[side], turret_hp=world.turret_hp))
    summary = dict(name=name, wins=sum(r['outcome'] == r['side'] for r in results),
                   matches=len(results), metrics={key: sum(r['metrics'][key] for r in results)
                                                for key in results[0]['metrics']})
    print(json.dumps(summary), flush=True)
    (HERE / ('guard_experiment_' + name + '.json')).write_text(
        json.dumps(dict(summary=summary, results=results), indent=2), encoding='utf-8')
    if name == 'both':
        (HERE.parent / 'team_logic.candidate.pyfrag').write_text(source, encoding='utf-8')

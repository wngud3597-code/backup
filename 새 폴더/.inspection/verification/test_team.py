"""Team safety/role checks in the independent six-tank model.

Run: python .inspection/verification/test_team.py
These checks verify rules and requested behavior, not multiplayer win rate.
"""
from collections import Counter
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(HERE))

from strategy_6_improved import TeamBot
from model import Model
from scenarios import blank
from team_world import World, play


class TeamTests(unittest.TestCase):
    def assert_safe(self,world,team):
        for metric in ('illegal','friendly','rock','empty','waits','errors'):
            self.assertEqual(world.metrics[team][metric],0,(team,metric,world.log[-10:]))

    def decide(self,bot,world,key):
        command = bot.choose(world.state(key))
        self.assertTrue(bot.validate(command),(key,command,bot.last_decision))
        return command

    def test_native_initial_roles_both_teams_all_maps(self):
        for map_index in range(4):
            for team in ('A','B'):
                with self.subTest(map=map_index,team=team):
                    world = World(map_index,seed=0)
                    roles = []
                    for slot in (1,2,3):
                        bot = TeamBot()
                        self.decide(bot,world,team+str(slot))
                        roles.append(bot.last_decision['role'])
                        self.assertEqual(bot.last_decision['unit_index'],slot)
                        self.assertEqual(bot.last_decision['assignment_source'],'verified_spawn_band')
                    self.assertEqual(roles,['defend1','defend2','attack'])

    def test_all_native_spawn_cells_infer_correct_unit_identity(self):
        for team in ('A','B'):
            for slot in (1,2,3):
                for r in range(12-slot*3,15-slot*3):
                    for c in (0,1):
                        with self.subTest(team=team,slot=slot,r=r,c=c):
                            world = World(0,seed=1)
                            key = team+str(slot)
                            world.units[key].pos = (r,c) if team == 'A' else (15-r,15-c)
                            bot = TeamBot()
                            self.decide(bot,world,key)
                            self.assertEqual(bot.last_decision['unit_index'],slot)
                            self.assertEqual(bot.last_decision['role'],('defend1','defend2','attack')[slot-1])

    def test_attacker_death_has_one_successor_and_last_survivor_attacks(self):
        for team in ('A','B'):
            with self.subTest(team=team):
                world = World(0,seed=0)
                bots = {slot:TeamBot() for slot in (1,2,3)}
                for slot,bot in bots.items():
                    command = self.decide(bot,world,team+str(slot))
                    world.apply(team+str(slot),command)
                world.units[team+'3'].hp = 0
                roles = []
                for slot in (1,2):
                    self.decide(bots[slot],world,team+str(slot))
                    roles.append(bots[slot].last_decision['role'])
                self.assertEqual(roles,['defend1','attack'])
                world.units[team+'2'].hp = 0
                self.decide(bots[1],world,team+'1')
                self.assertEqual(bots[1].last_decision['role'],'attack')

    def test_other_defender_death_does_not_create_two_attackers(self):
        for team in ('A','B'):
            with self.subTest(team=team):
                world = World(0,seed=0)
                bots = {slot:TeamBot() for slot in (1,2,3)}
                for slot in (1,2,3):
                    self.decide(bots[slot],world,team+str(slot))
                world.units[team+'1'].hp = 0
                roles = []
                for slot in (2,3):
                    self.decide(bots[slot],world,team+str(slot))
                    roles.append(bots[slot].last_decision['role'])
                self.assertEqual(roles,['defend2','attack'])

    def test_attack_succession_waits_for_intruder_to_retreat(self):
        for team in ('A','B'):
            with self.subTest(team=team):
                world = World(0,seed=0)
                enemy = 'B' if team == 'A' else 'A'
                bots = {slot:TeamBot() for slot in (1,2,3)}
                for slot,bot in bots.items():
                    command = self.decide(bot,world,team+str(slot))
                    world.apply(team+str(slot),command)
                world.units[team+'3'].hp = 0
                intruder = world.units[enemy+'1']
                original_enemy_position = intruder.pos
                intruder.pos = (12,3) if team == 'A' else (3,12)
                for slot in (1,2):
                    command = self.decide(bots[slot],world,team+str(slot))
                    self.assertEqual(bots[slot].last_decision['role'],'defend'+str(slot))
                    world.apply(team+str(slot),command)
                intruder.pos = original_enemy_position
                roles = []
                for slot in (1,2):
                    self.decide(bots[slot],world,team+str(slot))
                    roles.append(bots[slot].last_decision['role'])
                self.assertEqual(roles,['defend1','attack'])
                self.assertEqual(bots[2].last_decision['assigned_role'],'defend2')
                self.assert_safe(world,team)

    def test_all_enemy_tanks_gone_releases_guards_to_attack(self):
        for team in ('A','B'):
            with self.subTest(team=team):
                world = World(0,seed=0)
                enemy = 'B' if team == 'A' else 'A'
                for key,unit in world.units.items():
                    if unit.team == enemy:
                        unit.hp = 0
                for slot in (1,2,3):
                    bot = TeamBot()
                    self.decide(bot,world,team+str(slot))
                    self.assertEqual(bot.last_decision['role'],'attack')

    def test_fixed_defender_role_stays_fixed(self):
        world = World(0,seed=0)
        for unit in world.units.values():
            if unit.team == 'B':
                unit.hp = 0
        bot = TeamBot(role='defend1')
        self.decide(bot,world,'A3')
        self.assertEqual(bot.last_decision['role'],'defend1')

    def test_same_physical_snapshot_has_one_attacker_in_non_native_map(self):
        positions = {1:(0,7),2:(3,10),3:(6,0)}
        roles = []
        for own_slot in (1,2,3):
            rows = blank(11,11)
            rows[10][0],rows[0][10],rows[10][10] = 'H','X','E1'
            for slot,p in positions.items():
                rows[p[0]][p[1]] = 'M' if slot == own_slot else f'M{slot}'
            bot = TeamBot()
            bot.choose(Model(rows).state())
            roles.append(bot.last_decision['role'])
        self.assertEqual(Counter(roles),Counter({'defend1':1,'defend2':1,'attack':1}))

    def test_guards_patrol_100_turns_without_penalties_or_hp_loss_in_patrol(self):
        for map_index in range(4):
            for team in ('A','B'):
                with self.subTest(map=map_index,team=team):
                    world = World(map_index,seed=0)
                    bots = {slot:TeamBot() for slot in (1,2)}
                    tails = {slot:[] for slot in (1,2)}
                    for turn in range(100):
                        for slot,bot in bots.items():
                            key = team+str(slot)
                            command = self.decide(bot,world,key)
                            world.apply(key,command)
                            self.assertGreater(world.units[key].hp,0)
                            if turn >= 70:
                                tails[slot].append((world.units[key].pos,world.units[key].hp,
                                                    bot.last_decision['reason']))
                    self.assert_safe(world,team)
                    self.assertEqual(world.metrics[team]['actions'],200)
                    for samples in tails.values():
                        self.assertEqual(len({p for p,hp,reason in samples}),2)
                        self.assertEqual(len({hp for p,hp,reason in samples}),1)
                        self.assertEqual({reason for p,hp,reason in samples},{'guard_patrol_pair'})
                        for p,hp,reason in samples:
                            self.assertEqual(world.terrain[p[0]][p[1]],'G')

    def test_guard_pair_cache_ignores_tank_movement_and_refreshes_after_tree_change(self):
        for team in ('A','B'):
            with self.subTest(team=team):
                world = World(0,seed=0)
                bot = TeamBot()
                command = self.decide(bot,world,team+'1')
                world.apply(team+'1',command)
                old_signature = bot.guard_signature
                old_pairs = bot.guard_pairs
                teammate = world.units[team+'2']
                teammate.pos = (7,1) if team == 'A' else (8,14)
                self.decide(bot,world,team+'1')
                self.assertEqual(bot.guard_signature,old_signature)
                self.assertIs(bot.guard_pairs,old_pairs)
                tree = (10,2) if team == 'A' else (4,12)
                self.assertEqual(world.terrain[tree[0]][tree[1]],'T')
                world.terrain[tree[0]][tree[1]] = 'G'
                self.decide(bot,world,team+'1')
                self.assertNotEqual(bot.guard_signature,old_signature)
                self.assertIsNot(bot.guard_pairs,old_pairs)

    def test_guard_fires_at_three_cell_intrusion_both_teams(self):
        for team in ('A','B'):
            with self.subTest(team=team):
                world = World(0,seed=0)
                enemy = 'B' if team == 'A' else 'A'
                defender = world.units[team+'1']
                intruder = world.units[enemy+'1']
                defender.pos = (9,0) if team == 'A' else (6,15)
                intruder.pos = (9,3) if team == 'A' else (6,12)
                bot = TeamBot()
                command = self.decide(bot,world,team+'1')
                self.assertEqual(command,'R F' if team == 'A' else 'L F')
                self.assertEqual(bot.last_decision['reason'],'guard_engage_tank')
                world.apply(team+'1',command)
                self.assertEqual(intruder.hp,70)
                self.assert_safe(world,team)

    def test_eight_dynamic_self_matches_have_no_safety_violations(self):
        for map_index in range(4):
            for first in ('A','B'):
                with self.subTest(map=map_index,first=first):
                    world = World(map_index,seed=0)
                    bots = {key:TeamBot() for key in world.units}
                    outcome = play(world,bots,rounds=100,first=first)
                    self.assertIn(outcome,('A','B','draw','turn_limit'))
                    self.assert_safe(world,'A')
                    self.assert_safe(world,'B')


if __name__ == '__main__':
    unittest.main(verbosity=2)

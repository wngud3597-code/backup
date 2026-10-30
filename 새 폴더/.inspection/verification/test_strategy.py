"""Repeatable checks of the attacker using an independent verification model.

Run from the workspace: python .inspection/verification/test_strategy.py
This does not launch Unity or measure multiplayer win rate. Distributed battle
terrain is used with static opponents; the engine can end real matches earlier
after two enemy tank losses.
"""
import importlib.util
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import attack_bot
from model import DIRECTIONS, Model, run
from scenarios import (all_attack_scenarios, blank, empty_ammo_supply,
                       engine_battle_map, open_map, seeded_obstacles, trapped,
                       visible_enemy, water_shot)


def rotate_clockwise(model):
    size = len(model.rows)
    assert size == len(model.rows[0])
    return Model([list(row) for row in zip(*model.rows[::-1])], hp=model.hp,
                 normal=model.normal, mega=model.mega,
                 entity_hp=dict(model.entity_hp), codes=list(model.codes),
                 forbidden={(c,size-1-r) for r,c in model.forbidden})


class StrategyTests(unittest.TestCase):
    def assert_safe(self, model):
        for attribute in ('friendly_shots', 'rock_shots', 'no_ammo_shots',
                          'forbidden_moves', 'illegal_moves', 'supply_failures'):
            self.assertEqual(getattr(model, attribute), 0, attribute)

    def decide(self, model, config=None):
        bot = attack_bot.Bot(config)
        command = bot.choose(model.state())
        self.assertIsInstance(command, str)
        self.assertTrue(bot.validate(command), command)
        return bot, command

    def test_reachable_requirement_scenarios_destroy_turret(self):
        for name, model in all_attack_scenarios().items():
            with self.subTest(name=name):
                run(attack_bot.Bot(), model, max_turns=100)
                self.assertTrue(model.turret_destroyed, model.commands)
                self.assertGreater(model.hp, 0)
                self.assertNotIn('S', model.commands)
                self.assert_safe(model)

    def test_reproducible_obstacle_maps(self):
        for seed in range(30):
            with self.subTest(seed=seed):
                model = run(attack_bot.Bot(), seeded_obstacles(seed), max_turns=100)
                self.assertTrue(model.turret_destroyed, model.commands)
                self.assertGreater(model.hp, 0)
                self.assert_safe(model)

    def test_distributed_battle_terrain_both_teams_all_slots(self):
        source = HERE.parent/'engine'/'maps'/'all_maps.json'
        if not source.exists():
            self.skipTest('Extracted distributed battle terrain is unavailable')
        for map_index in range(4):
            for team in ('A', 'B'):
                for slot in (1, 2, 3):
                    with self.subTest(map=map_index, team=team, slot=slot):
                        model = engine_battle_map(map_index, team, slot)
                        run(attack_bot.Bot(), model, max_turns=100)
                        self.assertTrue(model.turret_destroyed, model.commands)
                        self.assertGreater(model.hp, 0)
                        self.assert_safe(model)

    def test_all_four_turret_corners(self):
        model = open_map(13, team=True)
        for corner in range(4):
            with self.subTest(corner=corner):
                initial = model
                # Use a fresh copy so the next rotated fixture is not mutated.
                model = rotate_clockwise(model)
                run(attack_bot.Bot(), initial, max_turns=100)
                self.assertTrue(initial.turret_destroyed, initial.commands)
                self.assert_safe(initial)

    def test_visible_enemy_tanks_all_directions_and_ranges(self):
        for direction, (dr,dc) in DIRECTIONS.items():
            for distance in (1, 2, 3):
                for hp in (30, 31, 70, 71, 100):
                    with self.subTest(direction=direction, distance=distance, hp=hp):
                        rows = blank(11, 11)
                        rows[5][5], rows[10][10] = 'M', 'X'
                        p = 5+dr*distance, 5+dc*distance
                        rows[p[0]][p[1]] = 'E1'
                        model = Model(rows, normal=5, mega=5, entity_hp={'E1':hp})
                        bot, command = self.decide(model)
                        self.assertEqual(bot.last_decision['reason'], 'engage_visible_tank')
                        self.assertEqual(command.split()[:2], [direction, 'F'])
                        if hp <= 30:
                            self.assertEqual(command, direction+' F')
                        model.apply(command)
                        self.assertLess(model.entity_hp['E1'], hp)
                        self.assert_safe(model)

    def test_out_of_range_enemy_does_not_replace_turret_goal(self):
        for distance in (4, 5, 6):
            with self.subTest(distance=distance):
                model = visible_enemy(distance)
                bot, command = self.decide(model)
                self.assertEqual(bot.last_decision['target'], 'X')
                self.assertEqual(bot.last_decision['reason'], 'planned_turret_attack')
                self.assertNotIn(' F', command)

    def test_diagonal_enemy_does_not_replace_turret_goal(self):
        rows = blank(11, 11)
        rows[5][5], rows[6][6], rows[10][10] = 'M', 'E1', 'X'
        bot, command = self.decide(Model(rows))
        self.assertEqual(bot.last_decision['target'], 'X')
        self.assertNotIn(' F', command)

    def test_turret_winning_shot_precedes_visible_tank(self):
        rows = blank(11, 11)
        rows[5][5], rows[5][8], rows[2][5] = 'M', 'X', 'E1'
        model = Model(rows, entity_hp={'X':30, 'E1':30})
        bot, command = self.decide(model)
        self.assertEqual(command, 'R F')
        self.assertEqual(bot.last_decision['reason'], 'destroy_turret_now')

    def test_visible_enemy_precedes_nonlethal_turret_damage(self):
        rows = blank(11, 11)
        rows[5][5], rows[5][8], rows[2][5] = 'M', 'X', 'E1'
        model = Model(rows, entity_hp={'X':100, 'E1':30})
        bot, command = self.decide(model)
        self.assertEqual(command, 'U F')
        self.assertEqual(bot.last_decision['target'], 'E1')

    def test_easier_visible_enemy_is_removed_first(self):
        rows = blank(11, 11)
        rows[5][5], rows[10][10], rows[2][5], rows[5][8] = 'M', 'X', 'E1', 'E2'
        model = Model(rows, entity_hp={'E1':100, 'E2':30})
        bot, command = self.decide(model)
        self.assertEqual(command, 'R F')
        self.assertEqual(bot.last_decision['target'], 'E2')

    def test_friends_rocks_supply_and_unknown_cells_block_shots(self):
        for direction, (dr,dc) in DIRECTIONS.items():
            for distance in (1, 2):
                for blocker in ('M1','M2','M3','H','R','F','Z'):
                    with self.subTest(direction=direction, distance=distance, blocker=blocker):
                        rows = blank(11, 11)
                        rows[5][5] = 'M'
                        rows[5+3*dr][5+3*dc] = 'X'
                        rows[5+distance*dr][5+distance*dc] = blocker
                        model = Model(rows, entity_hp={'X':30})
                        _, command = self.decide(model)
                        self.assertFalse(command.startswith(direction+' F'), command)
                        model.apply(command)
                        self.assert_safe(model)

    def test_water_and_sand_transmit_shells(self):
        for direction, (dr,dc) in DIRECTIONS.items():
            with self.subTest(direction=direction):
                rows = blank(11, 11)
                rows[5][5] = 'M'
                rows[5+dr][5+dc] = 'W'
                rows[5+2*dr][5+2*dc] = 'S'
                rows[5+3*dr][5+3*dc] = 'X'
                model = Model(rows, entity_hp={'X':30})
                _, command = self.decide(model)
                self.assertEqual(command, direction+' F')

    def test_zero_ammo_and_no_route_returns_emergency_wait(self):
        model = trapped()
        bot = attack_bot.Bot()
        for _ in range(5):
            command = bot.choose(model.state())
            self.assertEqual(command, 'S')
            self.assertTrue(bot.validate(command))
            self.assertTrue(bot.last_decision['emergency_wait'])
            model.apply(command)
        self.assert_safe(model)

    def test_lethal_sand_is_not_entered(self):
        rows = [['S']*7 for _ in range(7)]
        rows[3][3], rows[6][6] = 'M', 'X'
        model = Model(rows, hp=10, normal=0, mega=0)
        _, command = self.decide(model)
        self.assertEqual(command, 'S')

    def test_supply_is_found_from_a_distance_when_ammo_is_empty(self):
        model = empty_ammo_supply()
        model.rows[4][1] = 'G'
        model.rows[1][1] = 'M'
        model.positions['M'] = (1,1)
        self.assertEqual(model.state().splitlines()[0].split()[-1], '0')
        run(attack_bot.Bot(), model, max_turns=100)
        self.assertTrue(model.turret_destroyed, model.commands)
        self.assertGreaterEqual(model.supplies_used, 2)
        self.assert_safe(model)

    def test_supply_at_cap_is_never_requested(self):
        model = empty_ammo_supply()
        model.mega = 10
        _, command = self.decide(model)
        self.assertFalse(command.startswith('G '))

    def test_small_planning_budget_has_legal_fallback(self):
        model = seeded_obstacles(7)
        bot = attack_bot.Bot({'planning_ms':1, 'max_expansions':1})
        for _ in range(6):
            command = bot.choose(model.state())
            self.assertTrue(bot.validate(command))
            self.assertNotEqual(command, 'S')
            model.apply(command)
        self.assert_safe(model)


class CompatibilityTests(unittest.TestCase):
    def test_import_does_not_connect(self):
        with mock.patch('socket.create_connection', side_effect=AssertionError('Unexpected connection')):
            spec = importlib.util.spec_from_file_location('attacker_import_check', ROOT/'attack_bot.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.my_func))

    def test_cli_help_and_replay(self):
        help_result = subprocess.run([sys.executable,str(ROOT/'attack_bot.py'),'--help'],
                                     capture_output=True, text=True, encoding='utf-8', timeout=5)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        with tempfile.TemporaryDirectory(dir=HERE) as temp_dir:
            replay = Path(temp_dir)/'state.txt'
            replay.write_text(water_shot().state(), encoding='utf-8')
            result = subprocess.run([sys.executable,str(ROOT/'attack_bot.py'),'--replay',str(replay),'--explain'],
                                    capture_output=True, text=True, encoding='utf-8', timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'R F M')
        self.assertIn('command', result.stderr)

    def test_local_socket_init_prefix_fragmented_state_commands_and_end(self):
        model = water_shot()
        server_errors = []
        observed = []
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1',0))
            listener.listen(1)
            listener.settimeout(3)
            port = listener.getsockname()[1]

            def read_command(connection):
                data = bytearray()
                while not data.endswith(b' '):
                    part = connection.recv(4096)
                    if not part:
                        raise AssertionError('Client closed before command')
                    data.extend(part)
                return data.decode('utf-8')

            def serve():
                try:
                    with listener.accept()[0] as connection:
                        connection.settimeout(3)
                        observed.append(read_command(connection))
                        for _ in range(8):
                            state = model.state().rstrip('\n').encode('utf-8')
                            # The last numeric field is deliberately split.
                            chunks = [state[:5], state[5:-2], state[-2:-1], state[-1:]]
                            for chunk in chunks:
                                connection.sendall(chunk)
                                time.sleep(.002)
                            command = read_command(connection)
                            observed.append(command)
                            if not command.startswith('PREFIX'):
                                raise AssertionError('Missing launcher prefix')
                            model.apply(command[len('PREFIX'):].strip())
                            if model.turret_destroyed:
                                break
                        connection.sendall(b'0 0 0 0 0')
                except BaseException as exc:
                    server_errors.append(exc)

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            attack_bot.run(attack_bot.Bot(), nickname='compatibility', prefix='PREFIX', port=port)
            thread.join(timeout=4)
            self.assertFalse(thread.is_alive(), 'Local verification server did not finish')
        self.assertFalse(server_errors, server_errors)
        self.assertEqual(observed[0], 'PREFIXINIT compatibility ')
        self.assertEqual(observed[1:], ['PREFIXR F M ', 'PREFIXR F M '])
        self.assertTrue(model.turret_destroyed)

    def test_terminal_variants(self):
        for ending in (b'0', b'-1', b'0 0 0 0 0'):
            with self.subTest(ending=ending):
                receiver, sender = socket.socketpair()
                with receiver, sender:
                    sender.sendall(ending)
                    self.assertIsNone(attack_bot.receive(receiver))


if __name__ == '__main__':
    unittest.main(verbosity=2)

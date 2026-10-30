"""Independent, deliberately limited model for attacker verification.

This is NOT the distributed Battle SSAFY engine and cannot measure match win
rate. Opponents stay still; only movement, projectile collisions and ammunition
are modeled. The supplied engine confirms that any shell removes one tree.
"""
from dataclasses import dataclass, field


DIRECTIONS = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}
PASS_THROUGH = {'G', 'S', 'W'}
FRIENDLY = {'H', 'M1', 'M2', 'M3'}
ENEMIES = {'X', 'E1', 'E2', 'E3'}


@dataclass
class Model:
    rows: list[list[str]]
    hp: int = 100
    normal: int = 10
    mega: int = 5
    entity_hp: dict[str, int] = field(default_factory=dict)
    forbidden: set[tuple[int, int]] = field(default_factory=set)
    codes: list[str] = field(default_factory=list)
    cipher_shift: int = 9
    facing: str = 'U'
    underfoot: str = 'G'
    turns: int = 0
    shots: int = 0
    friendly_shots: int = 0
    rock_shots: int = 0
    wasted_shots: int = 0
    illegal_moves: int = 0
    no_ammo_shots: int = 0
    forbidden_moves: int = 0
    supplies_used: int = 0
    supply_failures: int = 0
    commands: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.rows = [list(row) for row in self.rows]
        assert self.rows and all(len(row) == len(self.rows[0]) for row in self.rows)
        self.positions = {}
        for r, row in enumerate(self.rows):
            for c, token in enumerate(row):
                if token == 'M' or token in FRIENDLY | ENEMIES:
                    assert token not in self.positions, 'Duplicate entity in model'
                    self.positions[token] = (r, c)
                    if token != 'M':
                        self.entity_hp.setdefault(token, 100)
        assert 'M' in self.positions

    @property
    def pos(self):
        return self.positions['M']

    @property
    def turret_destroyed(self):
        return self.entity_hp.get('X', 0) <= 0

    def inside(self, p):
        return 0 <= p[0] < len(self.rows) and 0 <= p[1] < len(self.rows[0])

    def state(self):
        # Explicit zero-HP records remain available after entity destruction.
        allies = {'M': f'{self.hp} {self.facing} {self.normal} {self.mega}'}
        enemies = {}
        for token, hp in self.entity_hp.items():
            (allies if token in FRIENDLY else enemies)[token] = str(hp)
        adjacent = any(self.inside((self.pos[0]+dr,self.pos[1]+dc)) and
                       self.rows[self.pos[0]+dr][self.pos[1]+dc] == 'F'
                       for dr,dc in DIRECTIONS.values())
        visible_codes = self.codes if adjacent else []
        return '\n'.join([
            f'{len(self.rows)} {len(self.rows[0])} {len(allies)} {len(enemies)} {len(visible_codes)}',
            *(' '.join(row) for row in self.rows),
            *(f'{token} {value}' for token, value in allies.items()),
            *(f'{token} {value}' for token, value in enemies.items()),
            *visible_codes,
        ]) + '\n'

    def first_collision(self, direction):
        dr, dc = DIRECTIONS[direction]
        for distance in range(1, 4):
            q = self.pos[0] + dr*distance, self.pos[1] + dc*distance
            if not self.inside(q):
                return None
            token = self.rows[q[0]][q[1]]
            if token not in PASS_THROUGH:
                return token, q
        return None

    def apply(self, command):
        assert isinstance(command, str), 'Bot must return text command'
        fields = command.split()
        self.turns += 1
        self.commands.append(command)
        if fields == ['S']:
            return
        if len(fields) == 2 and fields[0] == 'G':
            adjacent = any(self.inside((self.pos[0]+dr,self.pos[1]+dc)) and
                           self.rows[self.pos[0]+dr][self.pos[1]+dc] == 'F'
                           for dr,dc in DIRECTIONS.values())
            expected = {''.join(chr((ord(ch)-65+self.cipher_shift)%26+65) for ch in code)
                        for code in self.codes}
            if adjacent and fields[1] in expected and self.mega < 10:
                self.mega += 1
                self.supplies_used += 1
            else:
                self.supply_failures += 1
            return
        assert fields and fields[0] in DIRECTIONS, f'Unknown command: {command!r}'
        direction = fields[0]
        self.facing = direction
        if fields[1:] == ['A']:
            dr, dc = DIRECTIONS[direction]
            q = self.pos[0] + dr, self.pos[1] + dc
            if not self.inside(q) or self.rows[q[0]][q[1]] not in {'G', 'S'}:
                self.illegal_moves += 1
                return
            if q in self.forbidden:
                self.forbidden_moves += 1
            old = self.pos
            next_underfoot = self.rows[q[0]][q[1]]
            self.rows[old[0]][old[1]] = self.underfoot
            self.rows[q[0]][q[1]] = 'M'
            self.positions['M'], self.underfoot = q, next_underfoot
            if next_underfoot == 'S':
                self.hp -= 10
            return
        assert fields[1:] in (['F'], ['F', 'M']), f'Unknown command: {command!r}'
        mega = len(fields) == 3
        ammo = self.mega if mega else self.normal
        if ammo <= 0:
            self.no_ammo_shots += 1
            return
        if mega:
            self.mega -= 1
        else:
            self.normal -= 1
        self.shots += 1
        hit = self.first_collision(direction)
        if hit is None:
            self.wasted_shots += 1
            return
        token, p = hit
        damage = 70 if mega else 30
        if token in FRIENDLY:
            self.friendly_shots += 1
        elif token == 'R':
            self.rock_shots += 1
        elif token in ENEMIES:
            self.entity_hp[token] = max(0, self.entity_hp[token]-damage)
            if self.entity_hp[token] == 0:
                self.rows[p[0]][p[1]] = 'G'
                del self.positions[token]
        elif token == 'T':
            self.rows[p[0]][p[1]] = 'G'
        else:
            self.wasted_shots += 1


def run(bot, model, max_turns=200):
    """Run a static-opponent scenario, stopping at X destruction or own death."""
    for _ in range(max_turns):
        if model.turret_destroyed or model.hp <= 0:
            break
        model.apply(bot.choose(model.state()))
    return model

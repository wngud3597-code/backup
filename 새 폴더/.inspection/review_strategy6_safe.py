import ast
import json
import pathlib
import py_compile
import sys
import types

source_path = pathlib.Path(__file__).with_name('strategy_6.original.py')
py_compile.compile(str(source_path), cfile=str(source_path.with_suffix('.compile.pyc')), doraise=True)
tree = ast.parse(source_path.read_text(encoding='utf-8'), filename=str(source_path))
safe = []
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
        safe.append(node)
    elif isinstance(node, ast.Assign):
        names = {n.id for target in node.targets for n in ast.walk(target) if isinstance(n, ast.Name)}
        if names & {'sock', 'game_data'}:
            continue
        ast.literal_eval(node.value)  # Reject every non-literal initializer.
        safe.append(node)
module = types.ModuleType('strategy6_safe_review')
exec(compile(ast.Module(body=safe, type_ignores=[]), str(source_path), 'exec'), module.__dict__)
print('runtime:', sys.version.split()[0])
print('safe definitions loaded; original top-level connection excluded')

def make_state(rows, hp=100, normal=99, mega=0, allies=None, enemies=None):
    allies = allies or [('M', [hp, 'R', normal, mega])]
    enemies = enemies or [('X', [100])]
    lines = ['%d %d %d %d 0' % (len(rows), len(rows[0]), len(allies), len(enemies))]
    lines += [' '.join(row) for row in rows]
    lines += [name+' '+' '.join(map(str, values)) for name,values in allies + enemies]
    return module.State('\n'.join(lines))

empty = make_state([['G','G','X'],['G','M','G'],['G','G','G']], normal=0, mega=0)
print('zero ammo fire_cmd:', empty.fire_cmd(0, True))
mega_only = make_state([['G','G','X'],['G','M','G'],['G','G','G']], normal=0, mega=2)
print('normal requested with mega only:', mega_only.fire_cmd(0, False))
trapped = make_state([['X','R','R'],['R','M','S'],['R','R','R']], hp=10)
print('hp10 only sand neighbor safe_move:', trapped.safe_move())
tree_route = make_state([['R','R','R','R','R'],['M','T','G','G','X'],['R','R','R','R','R']], normal=0, mega=2)
print('mega only tree route:', tree_route.dijkstra({(1,2)}))

cached = make_state([['G']*6 for _ in range(6)])
cached.grid[5][0]='H';cached.my_turret=(5,0);cached.me=(2,1)
cached.enemy_tanks={'E1':(1,4)}
module._ROLE.clear()
module._ROLE['role']=('def',0)
module._ROLE['pairs']=[((2,1),(2,2))]
cached.grid[2][1]='M';cached.grid[2][2]='R'
print('cached pair points to rock; decision:', module.decide_guard2(cached,0))
print('cached pair remains:', module._ROLE['pairs'])

real_maps = json.loads(source_path.with_name('engine').joinpath('maps/all_maps.json').read_text())
grid = [['H' if cell == 'XA' else 'X' if cell == 'XB' else 'G' if cell in ('G1','G2') else cell
         for cell in row] for row in real_maps['stage0_map0']]
grid[10][0] = 'M'
state_text = '\n'.join(['16 16 2 1 0'] + [' '.join(row) for row in grid] +
                       ['M 100 R 99 0', 'H 100', 'X 100'])
parts = iter((state_text[:100].encode(), state_text[100:].encode()))
module.sock = types.SimpleNamespace(recv=lambda size: next(parts))
first_frame = module.receive()
print('normal official map frame bytes:', len(state_text.encode()))
print('100-byte TCP fragment accepted as frame:', len(first_frame))
print('partial frame command:', module.my_func(first_frame))
print('remaining frame accepted:', module.receive() is not None)

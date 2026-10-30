import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'pylibs'))
import dnfile
from dncil.cil.body.reader import read_method_body_from_bytes
from dncil.clr.token import Token, StringToken

p = dnfile.dnPE(str(HERE / 'Assembly-CSharp.dll'))
owners = {}
for typ in p.net.mdtables.TypeDef:
    for method in typ.MethodList:
        owners[method.row_index] = str(typ.TypeName)
    for field in typ.FieldList:
        owners[('field',field.row_index)] = str(typ.TypeName)

def resolve(operand):
    if isinstance(operand, StringToken):
        return repr(p.net.user_strings.get(operand.rid).value)
    if isinstance(operand, Token):
        table = p.net.mdtables.tables.get(operand.table)
        if table is None:
            return str(operand)
        item = table.rows[operand.rid-1]
        name = str(getattr(item, 'Name', getattr(item, 'TypeName', operand)))
        if operand.table == 6:
            return owners.get(operand.rid,'')+'.'+name
        if operand.table == 4:
            return owners.get(('field',operand.rid),'')+'.'+name
        if operand.table == 10:
            classname = item.Class.row
            return str(getattr(classname,'TypeName',getattr(classname,'Name','?')))+'.'+name
        return name
    return str(operand) if operand is not None else ''

targets = set(sys.argv[1:])
for idx, method in enumerate(p.net.mdtables.MethodDef, 1):
    qualname = owners[idx]+'.'+str(method.Name)
    if targets and not any(qualname.startswith(t) for t in targets):
        continue
    if not method.Rva:
        continue
    print('\n### '+qualname)
    body = read_method_body_from_bytes(p.get_data(method.Rva, 100000))
    for inst in body.instructions:
        print(f'{inst.offset:04x}  {inst.opcode.name:16} {resolve(inst.operand)}')

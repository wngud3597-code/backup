"""Compile/import/help verification using the exact bundled Python runtime."""
import hashlib
import importlib.util
import pathlib
import py_compile
import socket
import subprocess
import sys

bot_path = pathlib.Path(sys.argv[1]).resolve()
print('runtime:', sys.version.split()[0])
print('sha256:', hashlib.sha256(bot_path.read_bytes()).hexdigest())
py_compile.compile(str(bot_path), cfile=str(pathlib.Path(__file__).with_name('attack_bot.pyc')), doraise=True)
print('compile: PASS')

original_socket = socket.socket
def reject_import_socket(*args, **kwargs):
    raise RuntimeError('Import attempted to construct a socket')
socket.socket = reject_import_socket
try:
    spec = importlib.util.spec_from_file_location('runtime_verified_attack_bot', str(bot_path))
    bot_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = bot_module
    spec.loader.exec_module(bot_module)
finally:
    socket.socket = original_socket
print('import without connection: PASS')

result = subprocess.run([sys.executable, str(bot_path), '--help'], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=10)
print('help exit:', result.returncode)
print('help output bytes:', len(result.stdout))
if result.returncode != 0:
    print(repr(result.stderr))
    raise SystemExit(result.returncode)
assert b'usage:' in result.stdout
print('help: PASS')

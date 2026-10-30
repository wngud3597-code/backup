"""Launch three real bundled-Python clients against a local model server.

This checks the standalone file and wire contract; it does not run Unity.
"""
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT), str(HERE)]
from attack_bot import Bot
from team_world import World

RUNTIME = ROOT / ".inspection" / "runtime" / "python" / "python.exe"


class ThreeClientTests(unittest.TestCase):
    def run_three_clients(self, team):
        world = World(0, seed=0)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(3)
        listener.settimeout(10)
        port = listener.getsockname()[1]
        peers, children, errors = {}, [], []
        other = "B" if team == "A" else "A"
        opponents = {other + str(slot): Bot() for slot in (1, 2, 3)}

        def serve():
            try:
                for slot in (1, 2, 3):
                    connection, _ = listener.accept()
                    connection.settimeout(6)
                    initial = connection.recv(4096).decode("utf-8")
                    assert initial == "INIT SSAFY_Team ", initial
                    peers[team + str(slot)] = connection
                for _ in range(100):
                    for slot in (1, 2, 3):
                        for side in (team, other):
                            key = side + str(slot)
                            if world.units[key].hp <= 0:
                                continue
                            if side == team:
                                connection = peers[key]
                                frame = world.state(key).encode("utf-8")
                                connection.sendall(frame[:13])
                                time.sleep(0.001)
                                connection.sendall(frame[13:])
                                response = connection.recv(4096).decode("utf-8")
                                assert response.endswith(" "), response
                                command = response.strip()
                            else:
                                command = opponents[key].choose(world.state(key))
                            world.apply(key, command)
                            if world.outcome():
                                return
                raise AssertionError("Turn limit reached")
            except Exception as exc:
                errors.append(exc)
            finally:
                for connection in peers.values():
                    try:
                        connection.sendall(b"0 0 0 0 0")
                    except OSError:
                        pass
                    connection.close()
                listener.close()

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        # An isolated folder ensures that the standalone bot cannot accidentally
        # import a helper from the project; its path contains spaces and Korean.
        with tempfile.TemporaryDirectory(prefix="SSAFY 팀 코드 ") as isolated:
            target = Path(isolated) / "최종 팀 코드.py"
            target.write_bytes((ROOT / "strategy_6_improved.py").read_bytes())
            try:
                for slot in (1, 2, 3):
                    child = subprocess.Popen([str(RUNTIME), str(target), "--port", str(port)],
                                             cwd=isolated, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    children.append(child)
                    # Preserve connection order, as the real game assigns slots.
                    limit = time.perf_counter() + 5
                    while team + str(slot) not in peers and time.perf_counter() < limit:
                        time.sleep(0.005)
                    self.assertIn(team + str(slot), peers)
                for child in children:
                    stdout, stderr = child.communicate(timeout=30)
                    self.assertEqual(child.returncode, 0, stderr.decode("utf-8", "replace"))
            finally:
                for child in children:
                    if child.poll() is None:
                        child.kill()
                        child.communicate()
        worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors, repr(errors))
        for metric in ("illegal", "friendly", "rock", "empty", "waits", "errors"):
            self.assertEqual(world.metrics[team][metric], 0, metric)
        self.assertGreater(world.metrics[team]["actions"], 30)

    def test_a_team_three_bundled_python_processes(self):
        self.run_three_clients("A")

    def test_b_team_three_bundled_python_processes(self):
        self.run_three_clients("B")


if __name__ == "__main__":
    unittest.main(verbosity=2)

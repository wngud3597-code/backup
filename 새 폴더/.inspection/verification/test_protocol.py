"""Local TCP/launcher contract tests, not actual Unity game matches."""
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from model import Model
from scenarios import empty_ammo_supply, open_map, visible_enemy

spec = importlib.util.spec_from_file_location("attack_bot_under_test", ROOT / "attack_bot.py")
bot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_module)
RUNTIME = ROOT / ".inspection" / "runtime" / "python" / "python.exe"


class ReceiverTests(unittest.TestCase):
    def fragmented_receive(self, parts, final_lf=False):
        left, right = socket.socketpair()
        errors = []

        def sender():
            try:
                for part in parts:
                    right.sendall(part)
                    time.sleep(0.002)
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=sender)
        worker.start()
        try:
            result = bot_module.receive(left, "lines" if final_lf else "official")
            worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            return result
        finally:
            left.close()
            right.close()

    def test_no_final_newline_with_split_last_hp(self):
        data = open_map(10).state().rstrip("\n").encode("utf-8")
        self.assertTrue(data.endswith(b"X 100"))
        parts = [data[:7], data[7:43], data[43:-2], data[-2:-1], data[-1:]]
        result = self.fragmented_receive(parts)
        self.assertEqual(result.encode("utf-8"), data)
        self.assertEqual(bot_module.parse_data(result)[2]["X"], ["100"])

    def test_large_frame_over_original_1024_byte_buffer(self):
        data = open_map(32).state().rstrip("\n").encode("utf-8")
        self.assertGreater(len(data), 1024)
        result = self.fragmented_receive([data[i:i + 257] for i in range(0, len(data), 257)])
        self.assertEqual(result.encode("utf-8"), data)

    def test_line_transport(self):
        data = open_map(10).state().encode("utf-8")
        self.assertEqual(self.fragmented_receive([data[:-1], data[-1:]], True).encode("utf-8"), data)

    def test_real_engine_end_signal(self):
        self.assertIsNone(self.fragmented_receive([b"0 0 0 0 0"]))

    def test_legacy_end_signals(self):
        for signal in (b"0", b"-1"):
            with self.subTest(signal=signal):
                self.assertIsNone(self.fragmented_receive([signal]))

    def test_prefix_and_trailing_space(self):
        self.assertEqual(bot_module.wire_command("R F M", "test-prefix:"), b"test-prefix:R F M ")
        for bad in ("R F\nINIT fake", "R F\x00", "R F\r"):
            with self.subTest(bad=bad):
                with self.assertRaises(bot_module.ProtocolError):
                    bot_module.wire_command(bad)


class LauncherTests(unittest.TestCase):
    def run_match(self, model, prefix=""):
        """Real shipped Python launches the one file and plays a mock server."""
        self.assertTrue(RUNTIME.is_file(), "Extract the supplied Python runtime first")
        errors, metrics = [], {}
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        server.settimeout(10)
        port = server.getsockname()[1]

        def serve():
            try:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(7)  # engine's 6s action limit + test tolerance
                    initial = connection.recv(4096).decode("utf-8")
                    assert initial == prefix + "INIT SSAFY_Attack ", initial
                    for turn in range(100):
                        payload = model.state().rstrip("\n").encode("utf-8")
                        # Split both within the header and within unit HP digits.
                        for part in (payload[:5], payload[5:-2], payload[-2:]):
                            connection.sendall(part)
                            time.sleep(0.001)
                        started = time.perf_counter()
                        response = connection.recv(4096).decode("utf-8")
                        metrics["max_response_ms"] = max(metrics.get("max_response_ms", 0),
                                                          (time.perf_counter() - started) * 1000)
                        assert response.startswith(prefix) and response.endswith(" "), response
                        command = response[len(prefix):].strip()
                        model.apply(command)
                        if model.turret_destroyed:
                            connection.sendall(b"0 0 0 0 0")
                            break
                    else:
                        raise AssertionError("Mock match did not destroy X in 100 turns")
            except Exception as exc:
                errors.append(exc)
            finally:
                server.close()

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        args = [str(RUNTIME), str(ROOT / "attack_bot.py")]
        if prefix:
            args.append(prefix)
        args.extend(["--port", str(port)])
        child = subprocess.Popen(args, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = child.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            stdout, stderr = child.communicate()
            self.fail("Bot subprocess hung: " + stderr.decode("utf-8", "replace"))
        worker.join(10)
        self.assertFalse(worker.is_alive(), "Mock server did not finish")
        self.assertFalse(errors, repr(errors))
        self.assertEqual(child.returncode, 0, stderr.decode("utf-8", "replace"))
        self.assertTrue(model.turret_destroyed)
        self.assertEqual(model.friendly_shots + model.rock_shots + model.wasted_shots +
                         model.no_ammo_shots + model.illegal_moves + model.forbidden_moves, 0)
        self.assertLess(metrics["max_response_ms"], 6000)
        return model

    def test_bundled_python_a_side(self):
        self.run_match(open_map(16, team=True))

    def test_bundled_python_b_side_with_prefix(self):
        self.run_match(open_map(16, mirror=True, team=True), "TEST:")

    def test_bundled_python_empty_ammo_supply(self):
        result = self.run_match(empty_ammo_supply())
        self.assertGreater(result.supplies_used, 0)
        self.assertEqual(result.supply_failures, 0)

    def test_bundled_python_tank_encounter_then_turret(self):
        result = self.run_match(visible_enemy(distance=3, hp=70))
        self.assertEqual(result.entity_hp["E1"], 0)
        self.assertTrue(result.commands[0].startswith("R F"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

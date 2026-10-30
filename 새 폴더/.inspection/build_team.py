"""Development-only assembler. The generated team bot is fully standalone."""
from pathlib import Path

root = Path(__file__).resolve().parent.parent
source = (root / "attack_bot.py").read_text(encoding="utf-8")
fragment = (root / ".inspection" / "team_logic.pyfrag").read_text(encoding="utf-8")
marker = "_default_bot = None"
assert source.count(marker) == 1
source = source.replace(marker, fragment + "\n\n" + marker)
source = source.replace("Battle SSAFY 1.3 attacker. Python 3.9+, standard library only.",
                        "Battle SSAFY 1.3 team: one attacker + two home guards. Python 3.9+.")
source = source.replace("NICKNAME = \"SSAFY_Attack\"", "NICKNAME = \"SSAFY_Team\"")
source = source.replace("_default_bot = Bot()", "_default_bot = TeamBot()")
source = source.replace("description=\"Battle SSAFY v1.3 turret attacker (Python 3.9+)\"",
                        "description=\"Battle SSAFY v1.3 team: 1 attacker + 2 guards (Python 3.9+)\"")
needle = '    parser.add_argument("--nickname", default=NICKNAME)'
assert source.count(needle) == 1
source = source.replace(needle, needle + '\n    parser.add_argument("--role", choices=("auto", "attack", "defend1", "defend2"), default="auto")')
assert source.count("    bot = Bot(config)") == 1
source = source.replace("    bot = Bot(config)", "    bot = TeamBot(config, role=args.role)")
source = source.replace("Run this file from the game's Python source picker, or run `python attack_bot.py`.",
                        "All three teammates can use this single file. Default roles are automatic.\n"
                        "The two tanks starting closest to H guard home; the remaining tank attacks X.\n"
                        "Run it from the game's Python source picker, or run this file with Python.")
(root / "strategy_6_improved.py").write_text(source, encoding="utf-8", newline="\n")
print("Built standalone strategy_6_improved.py")

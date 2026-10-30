"""Limited independent-model comparison. Results are NOT real game win rates."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT), str(HERE)]
from compare_strategy6 import load_strategy6
from team_world import World, play
from strategy_6_improved import TeamBot


class OriginalTeam:
    def __init__(self):
        self.namespace = load_strategy6()

    def choose(self, state):
        return self.namespace["decide_s6"](self.namespace["State"](state))


def main():
    results = []
    for map_index in range(4):
        for side in ("A", "B"):
            for first in ("A", "B"):
                world = World(map_index, seed=0)
                controllers = {key: TeamBot() if key[0] == side else OriginalTeam() for key in world.units}
                outcome = play(world, controllers, first=first)
                results.append({"map":map_index, "improved_side":side, "first":first,
                                "outcome":outcome, "turret_hp":world.turret_hp,
                                "metrics":world.metrics})
    summary = {"independent_model_only":True, "matches":len(results),
               "improved_wins":sum(r["outcome"]==r["improved_side"] for r in results),
               "original_wins":sum(r["outcome"] in ("A","B") and r["outcome"]!=r["improved_side"] for r in results),
               "draw_or_turn_limit":sum(r["outcome"] not in ("A","B") for r in results)}
    output = {"summary":summary,"results":results}
    (HERE/"team_comparison.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary))
    for side_type in ("improved", "original"):
        metrics = {key:0 for key in results[0]["metrics"]["A"]}
        for r in results:
            side = r["improved_side"] if side_type=="improved" else ("B" if r["improved_side"]=="A" else "A")
            for key,value in r["metrics"][side].items():
                metrics[key] += value
        print(side_type,json.dumps(metrics))


if __name__ == "__main__":
    main()

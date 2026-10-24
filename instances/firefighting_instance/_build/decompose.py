# -*- coding: utf-8 -*-
"""Decompose the fitness of every baseline run into reward / fly / delay / penalty."""
import json
from pathlib import Path

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
EX = ROOT / "example"

results = json.loads((BUILD / "solve_results.json").read_text(encoding="utf-8"))
inst_cache = {}
for iid in sorted({r["instance_id"] for r in results}):
    d = json.loads((EX / f"firefighting_instance_{iid:03d}.json").read_text(encoding="utf-8"))
    inst_cache[iid] = (d, {t["id"]: t for t in d["tasks"]},
                       {p["id"]: p for p in d["fire_points"]})

rows = []
for r in results:
    d, tmap, fmap = inst_cache[r["instance_id"]]
    log = r["execution_log"]
    reward = sum(3 * fmap[fid]["value0"] * fmap[fid]["hp"]
                 for fid in {e["fire_id"] for e in log if e["type"] == 3})
    delay = sum((e["start_time"] - tmap[e["task_id"]]["window_end"]) * 10
                for e in log if e["type"] == 2 and tmap[e["task_id"]]["window_end"] is not None
                and e["start_time"] > tmap[e["task_id"]]["window_end"])
    fly = reward - delay - r["net_reward"]
    penalty = r["constraint_violation"] * 1000
    rows.append({
        "iid": r["instance_id"], "seed": r["seed"], "fitness": r["fitness"],
        "reward": round(reward, 2), "delay": round(delay, 2), "fly": round(fly, 2),
        "penalty": round(penalty, 2), "fires": r["completed_fires"],
        "cv": r["constraint_violation"], "makespan": r["makespan"],
        "km": round(fly / 3, 2), "sec": r["seconds"],
        "full_reward": round(sum(3 * p["value0"] * p["hp"] for p in d["fire_points"]), 2),
    })

print(f"{'iid':>3} {'seed':>4} {'fitness':>9} {'reward':>9} {'fly':>9} {'delay':>7} "
      f"{'penalty':>8} {'fires':>5} {'cv':>4} {'km':>8}")
for r in rows:
    print(f"{r['iid']:>3} {r['seed']:>4} {r['fitness']:>9.2f} {r['reward']:>9.2f} {r['fly']:>9.2f} "
          f"{r['delay']:>7.2f} {r['penalty']:>8.2f} {r['fires']:>5} {r['cv']:>4.1f} {r['km']:>8.2f}")

for label, ids in [("批次A (1,10,20)", (1, 10, 20)), ("批次B (31,40,50)", (31, 40, 50))]:
    sub = [r for r in rows if r["iid"] in ids]
    if not sub:
        continue
    print(f"\n{label}: n={len(sub)}  fitness {min(r['fitness'] for r in sub):.0f}~"
          f"{max(r['fitness'] for r in sub):.0f}  平均延误 "
          f"{sum(r['delay'] for r in sub)/len(sub):.1f}  平均航程 "
          f"{sum(r['km'] for r in sub)/len(sub):.1f} km  漏灭火点次数 "
          f"{sum(1 for r in sub if r['fires'] < 25)}")

worst = min(rows, key=lambda r: r["fitness"])
best = max(rows, key=lambda r: r["fitness"])
print(f"\n最差运行 iid={worst['iid']} seed={worst['seed']}: fitness={worst['fitness']:.2f}, "
      f"奖励 {worst['reward']:.2f}, 罚值 {worst['penalty']:.2f}")
print(f"最佳运行 iid={best['iid']} seed={best['seed']}: fitness={best['fitness']:.2f}, "
      f"奖励 {best['reward']:.2f}, 罚值 {best['penalty']:.2f}")
if worst["iid"] == best["iid"]:
    print(f"同实例差距 {best['fitness'] - worst['fitness']:.2f} = 奖励差 "
          f"{best['reward'] - worst['reward']:.2f} + 罚值差 {worst['penalty'] - best['penalty']:.2f} "
          f"+ (飞行/延误差 {-( (best['fly']+best['delay']) - (worst['fly']+worst['delay']) ):.2f})")

(BUILD / "decompose.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

# -*- coding: utf-8 -*-
"""Collect instance-suite statistics and the full data tables of instance 001.

Outputs: _build/stats.json
"""
import hashlib
import json
import statistics as st
from pathlib import Path

ROOT = Path(r"C:\kares_main\instances\firefighting_instance")
EX = ROOT / "example"
UAV_DIR = Path(r"C:\kares_main\instances\uav")
OUT = Path(__file__).resolve().parent / "stats.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


files = sorted(EX.glob("firefighting_instance_*.json"))
print("instances:", len(files))

per_instance = []
hash_match = {}
for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    iid = data["instance_id"]
    uavs = data["uavs"]
    fps = data["fire_points"]
    tasks = data["tasks"]
    hp = [p["hp"] for p in fps]
    val = [p["value0"] for p in fps]
    ws = [p["window_start"] for p in fps]
    we = [p["window_end"] for p in fps]
    width = [e - s for s, e in zip(ws, we)]
    xs = [p["pos"][0] for p in fps]
    ys = [p["pos"][1] for p in fps]
    full_reward = sum(3 * v * h for v, h in zip(val, hp))

    other = UAV_DIR / f.name
    hash_match[f.name] = (sha256(f) == sha256(other)) if other.exists() else None

    per_instance.append({
        "instance_id": iid,
        "n_uavs": len(uavs),
        "n_scout": sum(1 for u in uavs if u["type"] == "scout"),
        "n_fighter": sum(1 for u in uavs if u["type"] == "fighter"),
        "n_fire": len(fps),
        "n_tasks": len(tasks),
        "hp_counts": {str(k): hp.count(k) for k in (1, 2, 3)},
        "hp_total": sum(hp),
        "value_min": min(val), "value_max": max(val), "value_mean": st.fmean(val),
        "ws_min": min(ws), "ws_max": max(ws), "ws_mean": st.fmean(ws),
        "we_min": min(we), "we_max": max(we),
        "width_min": min(width), "width_max": max(width), "width_mean": st.fmean(width),
        "x_min": min(xs), "x_max": max(xs), "y_min": min(ys), "y_max": max(ys),
        "reward_all_fires": full_reward,
        "task_ids_contiguous": [t["id"] for t in tasks] == list(range(1, len(tasks) + 1)),
        "task_type_counts": {str(k): sum(1 for t in tasks if t["type"] == k) for k in (1, 2, 3)},
    })

agg = {
    "n_instances": len(per_instance),
    "all_25_fire": all(p["n_fire"] == 25 for p in per_instance),
    "all_75_tasks": all(p["n_tasks"] == 75 for p in per_instance),
    "all_16_uavs": all(p["n_uavs"] == 16 for p in per_instance),
    "all_type_split": all(p["n_scout"] == 4 and p["n_fighter"] == 12 for p in per_instance),
    "hash_identical_to_instances_uav": all(v is True for v in hash_match.values()),
    "hash_checked": len(hash_match),
    "hp_counts_total": {str(k): sum(p["hp_counts"][str(k)] for p in per_instance) for k in (1, 2, 3)},
    "value_min": min(p["value_min"] for p in per_instance),
    "value_max": max(p["value_max"] for p in per_instance),
    "value_mean_of_means": st.fmean([p["value_mean"] for p in per_instance]),
    "ws_min": min(p["ws_min"] for p in per_instance),
    "ws_max": max(p["ws_max"] for p in per_instance),
    "we_min": min(p["we_min"] for p in per_instance),
    "we_max": max(p["we_max"] for p in per_instance),
    "width_min": min(p["width_min"] for p in per_instance),
    "width_max": max(p["width_max"] for p in per_instance),
    "width_mean": st.fmean([p["width_mean"] for p in per_instance]),
    "reward_all_fires_min": min(p["reward_all_fires"] for p in per_instance),
    "reward_all_fires_max": max(p["reward_all_fires"] for p in per_instance),
    "reward_all_fires_mean": st.fmean([p["reward_all_fires"] for p in per_instance]),
    "total_tasks": sum(p["n_tasks"] for p in per_instance),
    "total_fire_points": sum(p["n_fire"] for p in per_instance),
    "total_hp": sum(p["hp_total"] for p in per_instance),
}

# --- full detail of instance 001 ---
d1 = json.loads((EX / "firefighting_instance_001.json").read_text(encoding="utf-8"))
detail = {
    "instance_id": d1["instance_id"],
    "uavs": [{"id": u["id"], "type": u["type"], "pos": u["pos"], "speed": u["speed"],
              "max_range": u["max_range"], "ammo": u["ammo"]} for u in d1["uavs"]],
    "fire_points": [{"id": p["id"], "x": round(p["pos"][0], 2), "y": round(p["pos"][1], 2),
                     "value": round(p["value0"], 2), "hp": p["hp"],
                     "ws": round(p["window_start"], 2), "we": round(p["window_end"], 2),
                     "width": round(p["window_end"] - p["window_start"], 2),
                     "reward": round(3 * p["value0"] * p["hp"], 2)} for p in d1["fire_points"]],
}
detail["reward_all_fires"] = round(sum(f["reward"] for f in detail["fire_points"]), 2)

# window overlap structure for one fire point (task chain illustration)
fp10 = [p for p in d1["fire_points"] if p["id"] == 10][0]
detail["worked_fire_point"] = {
    "id": fp10["id"], "x": round(fp10["pos"][0], 2), "y": round(fp10["pos"][1], 2),
    "value": round(fp10["value0"], 4), "hp": fp10["hp"],
    "ws": round(fp10["window_start"], 4), "we": round(fp10["window_end"], 4),
    "reward": round(3 * fp10["value0"] * fp10["hp"], 4),
}

# --- batch comparison: the suite contains two time-window regimes ---
batches = {}
for label, lo, hi in [("batch_A_001_030", 1, 30), ("batch_B_031_050", 31, 50)]:
    rows = [p for p in per_instance if lo <= p["instance_id"] <= hi]
    ws_lo = min(p["ws_min"] for p in rows)
    ws_hi = max(p["ws_max"] for p in rows)
    w_lo = min(p["width_min"] for p in rows)
    w_hi = max(p["width_max"] for p in rows)
    batches[label] = {
        "instances": f"{lo}-{hi}",
        "count": len(rows),
        "ws_min": ws_lo, "ws_max": ws_hi,
        "width_min": w_lo, "width_max": w_hi,
        "width_mean": st.fmean([p["width_mean"] for p in rows]),
        "hp_counts": {str(k): sum(p["hp_counts"][str(k)] for p in rows) for k in (1, 2, 3)},
        "value_mean": st.fmean([p["value_mean"] for p in rows]),
        "reward_all_fires_mean": st.fmean([p["reward_all_fires"] for p in rows]),
        "n_instances_with_width_gt_200": sum(1 for p in rows if p["width_max"] > 200.5),
    }

out = {
    "per_instance": per_instance,
    "aggregate": agg,
    "batches": batches,
    "instance_001": detail,
    "hash_match": hash_match,
}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(agg, ensure_ascii=False, indent=2))
print("instance_001 all-fire reward:", detail["reward_all_fires"])
print("worked fire point:", detail["worked_fire_point"])
print("written:", OUT)

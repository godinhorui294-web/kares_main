# -*- coding: utf-8 -*-
"""Generate UAV firefighting instances (10f / 25f / 50f) matching the
distribution of the existing benchmark set.

Layout per scale (identical across all instances of that scale):
  10f: 2 scouts at (5,5),(7,7); 6 fighters on the (9,9)..(19,19) diagonal
  25f: 4 scouts at (1,1)..(7,7); 12 fighters on the (9,9)..(31,31) diagonal
  50f: 8 scouts at (1,1),(3,3),(5,5),(7,7),(9,1),(1,9),(5,9),(9,5);
       24 fighters alternating (odd,odd)/(even,even-2) from (9,9) to (32,30)

Fires: position uniform x~[20,100], y~[10,90]; value0 uniform [50,100];
hp uniform in {1,2,3}; window_start uniform [0,500];
window_end = window_start + uniform [100,350].

Each fire yields 3 tasks (recon -> attack -> reinspect); only the attack
task carries hp and the time window.

Usage:
  python tools/generate_uav_instances.py --scale 10 --count 20 --start-index 11
  python tools/generate_uav_instances.py --scale 50 --count 20 --start-index 11
"""
import argparse
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UAV_DIR = os.path.join(ROOT, "instances", "uav")

SCOUT_POS = {
    10: [(5, 5), (7, 7)],
    25: [(1, 1), (3, 3), (5, 5), (7, 7)],
    50: [(1, 1), (3, 3), (5, 5), (7, 7), (9, 1), (1, 9), (5, 9), (9, 5)],
}


def fighter_positions(scale):
    if scale == 10:
        return [(9 + 2 * k, 9 + 2 * k) for k in range(6)]
    if scale == 25:
        return [(9 + 2 * k, 9 + 2 * k) for k in range(12)]
    if scale == 50:
        return [(9 + k, 9 + k if k % 2 == 0 else 7 + k) for k in range(24)]
    raise ValueError(scale)


def build_instance(instance_id, scale, rng):
    uavs = []
    uid = 1
    for x, y in SCOUT_POS[scale]:
        uavs.append({"id": uid, "type": "scout", "pos": [x, y, 10],
                     "speed": 0.5, "max_range": 1000, "ammo": 0})
        uid += 1
    for i, (x, y) in enumerate(fighter_positions(scale)):
        uavs.append({"id": uid, "type": "fighter", "pos": [x, y, 10],
                     "speed": 0.5, "max_range": 800, "ammo": 6 if i < 2 else 5})
        uid += 1

    fire_points, tasks = [], []
    for fid in range(1, scale + 1):
        pos = [rng.uniform(20, 100), rng.uniform(10, 90), 0]
        value0 = rng.uniform(50, 100)
        hp = rng.randint(1, 3)
        window_start = rng.uniform(0, 500)
        window_end = window_start + rng.uniform(100, 350)
        fire_points.append({"id": fid, "pos": pos, "value0": value0, "hp": hp,
                            "window_start": window_start, "window_end": window_end})
        tasks.append({"id": 3 * fid - 2, "fire_id": fid, "type": 1, "pos": list(pos),
                      "hp": 0, "window_start": None, "window_end": None, "duration": 0.0})
        tasks.append({"id": 3 * fid - 1, "fire_id": fid, "type": 2, "pos": list(pos),
                      "hp": hp, "window_start": window_start, "window_end": window_end,
                      "duration": 0.0})
        tasks.append({"id": 3 * fid, "fire_id": fid, "type": 3, "pos": list(pos),
                      "hp": 0, "window_start": None, "window_end": None, "duration": 0.0})

    return {"instance_id": instance_id, "uavs": uavs,
            "fire_points": fire_points, "tasks": tasks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=int, required=True, choices=[10, 25, 50])
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--start-index", type=int, required=True,
                    help="first instance serial number, e.g. 11 -> _011")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    rng = random.Random(args.seed + args.scale * 1000)
    out_dir = os.path.join(UAV_DIR, "%df" % args.scale)
    os.makedirs(out_dir, exist_ok=True)
    id_base = args.scale * 1000 if args.scale in (10, 50) else 0

    for i in range(args.start_index, args.start_index + args.count):
        inst = build_instance(id_base + i, args.scale, rng)
        if args.scale == 25:
            name = "firefighting_instance_%03d.json" % i
        else:
            name = "firefighting_instance_%df_%03d.json" % (args.scale, i)
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(inst, f, indent=2)
        print("wrote", path)


if __name__ == "__main__":
    main()

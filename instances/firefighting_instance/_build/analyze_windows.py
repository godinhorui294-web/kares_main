# -*- coding: utf-8 -*-
"""Characterise the empirical distributions of the instance generator."""
import json
from collections import Counter
from pathlib import Path

import numpy as np

EX = Path(r"C:\kares_main\instances\firefighting_instance\example")
files = sorted(EX.glob("firefighting_instance_*.json"))

ws_all, we_all, w_all, val_all, hp_all, x_all, y_all = [], [], [], [], [], [], []
per_inst_width_min, per_inst_width_max = [], []
for f in files:
    d = json.loads(f.read_text(encoding="utf-8"))
    fps = d["fire_points"]
    w = [p["window_end"] - p["window_start"] for p in fps]
    ws_all += [p["window_start"] for p in fps]
    we_all += [p["window_end"] for p in fps]
    w_all += w
    val_all += [p["value0"] for p in fps]
    hp_all += [p["hp"] for p in fps]
    x_all += [p["pos"][0] for p in fps]
    y_all += [p["pos"][1] for p in fps]
    per_inst_width_min.append(min(w))
    per_inst_width_max.append(max(w))

for name, a in [("window_start", ws_all), ("window_end", we_all), ("width", w_all),
                ("value", val_all), ("x", x_all), ("y", y_all)]:
    a = np.asarray(a)
    print(f"{name:>12}: n={len(a)} min={a.min():.4f} max={a.max():.4f} mean={a.mean():.4f} "
          f"std={a.std():.4f} q05={np.quantile(a,0.05):.2f} q50={np.quantile(a,0.5):.2f} q95={np.quantile(a,0.95):.2f}")

hist, edges = np.histogram(w_all, bins=np.arange(80, 380, 20))
print("\nwidth histogram (bin start: count):")
for h, e in zip(hist, edges):
    print(f"  {e:6.0f}-{e+20:6.0f}: {h:5d}  {'#' * (h // 8)}")

print("\nper-instance width range: min over instances", round(min(per_inst_width_min), 2),
      "max over instances", round(max(per_inst_width_max), 2))
print("instances whose max width <= 200:", sum(1 for m in per_inst_width_max if m <= 200.001))
print("hp counts:", Counter(hp_all))
print("\nvalue within [50,100]:", min(val_all) >= 50 and max(val_all) <= 100)
print("x within [20,100]:", min(x_all) >= 20 and max(x_all) <= 100)
print("y within [10,90]:", min(y_all) >= 10 and max(y_all) <= 90)
print("ws within [0,500]:", min(ws_all) >= 0 and max(ws_all) <= 500)
print("we within [100,700]:", min(we_all) >= 100 and max(we_all) <= 700)
print("width >= 100:", min(w_all) >= 100 - 1e-9)

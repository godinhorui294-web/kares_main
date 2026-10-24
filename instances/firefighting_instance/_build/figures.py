# -*- coding: utf-8 -*-
"""Generate the figures used by the Word case-study document."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

BUILD = Path(__file__).resolve().parent
FIG = BUILD / "figures"
FIG.mkdir(exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 300
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["font.size"] = 9

from matplotlib import font_manager as fm
avail = {f.name for f in fm.fontManager.ttflist}
print("CJK font pick:", [n for n in ("Microsoft YaHei", "SimHei", "SimSun") if n in avail])

stats = json.loads((BUILD / "stats.json").read_text(encoding="utf-8"))
smoke = json.loads((BUILD / "solve_smoke.json").read_text(encoding="utf-8"))[0]
inst = stats["instance_001"]
uavs = inst["uavs"]
fps = inst["fire_points"]

# ---------------------------------------------------------------- Fig 1 layout
fig, ax = plt.subplots(figsize=(6.1, 4.6))
vals = np.array([f["value"] for f in fps])
hp = np.array([f["hp"] for f in fps])
sc = ax.scatter([f["x"] for f in fps], [f["y"] for f in fps],
                s=28 * hp ** 1.6, c=vals, cmap="autumn_r", edgecolors="k",
                linewidths=0.5, zorder=3)
for f in fps:
    ax.annotate(str(f["id"]), (f["x"], f["y"]), textcoords="offset points",
                xytext=(5, 4), fontsize=6.5, zorder=4)
scout = [u for u in uavs if u["type"] == "scout"]
fight = [u for u in uavs if u["type"] == "fighter"]
ax.scatter([u["pos"][0] for u in scout], [u["pos"][1] for u in scout], marker="^",
           s=70, c="#1f77b4", edgecolors="k", linewidths=0.5, label="侦察机 (UAV1–4)", zorder=5)
ax.scatter([u["pos"][0] for u in fight], [u["pos"][1] for u in fight], marker="s",
           s=34, c="#d62728", edgecolors="k", linewidths=0.4, label="灭火机 (UAV5–16)", zorder=5)
ax.scatter([25], [25], marker="*", s=230, c="k", label="基地 [25,25]", zorder=6)
ax.set_xlabel("x / km")
ax.set_ylabel("y / km")
ax.set_xlim(0, 108)
ax.set_ylim(0, 100)
ax.grid(alpha=0.25, linestyle=":")
ax.legend(loc="upper right", fontsize=7.5, framealpha=0.95)
cb = fig.colorbar(sc, ax=ax, pad=0.02)
cb.set_label("保护价值 $V_j$", fontsize=8)
hs = [Line2D([], [], marker="o", linestyle="", color="gray",
             markersize=np.sqrt(28 * h ** 1.6) / 3, label=f"HP={h}") for h in (1, 2, 3)]
ax.legend(handles=ax.get_legend_handles_labels()[0] + hs, loc="lower right", fontsize=7.5,
          framealpha=0.95)
fig.savefig(FIG / "fig1_layout.png")
plt.close(fig)
print("fig1 done")

# ------------------------------------------------------- Fig 2 parameter stats
per = stats["per_instance"]
hp_all, val_all, ws_all, w_all, w_batchA, w_batchB = [], [], [], [], [], []
for f in sorted((BUILD.parent / "example").glob("*.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    for p in d["fire_points"]:
        hp_all.append(p["hp"])
        val_all.append(p["value0"])
        ws_all.append(p["window_start"])
        w = p["window_end"] - p["window_start"]
        w_all.append(w)
        (w_batchA if d["instance_id"] <= 30 else w_batchB).append(w)

fig, axes = plt.subplots(2, 2, figsize=(6.3, 4.6))
ax = axes[0][0]
cnt = [hp_all.count(k) for k in (1, 2, 3)]
bars = ax.bar(["HP=1", "HP=2", "HP=3"], cnt, color=["#74add1", "#fdae61", "#d73027"],
              edgecolor="k", linewidth=0.5)
for b, c in zip(bars, cnt):
    ax.text(b.get_x() + b.get_width() / 2, c + 6, f"{c}\n({c/len(hp_all)*100:.1f}%)",
            ha="center", fontsize=7)
ax.set_ylim(0, max(cnt) * 1.28)
ax.set_ylabel("火点数量")
ax.set_title("(a) 火势等级 $HP_j$ 分布（1250 个火点）", fontsize=8.5)
ax.grid(alpha=0.2, axis="y", linestyle=":")

ax = axes[0][1]
ax.hist(val_all, bins=20, color="#4575b4", edgecolor="white", linewidth=0.4)
ax.axvline(np.mean(val_all), color="r", linestyle="--", linewidth=1,
           label=f"均值 {np.mean(val_all):.1f}")
ax.set_xlabel("保护价值 $V_j$")
ax.set_ylabel("火点数量")
ax.set_title("(b) 保护价值 $V_j$ 分布", fontsize=8.5)
ax.legend(fontsize=7)
ax.grid(alpha=0.2, axis="y", linestyle=":")

ax = axes[1][0]
ax.hist(w_batchA, bins=np.arange(100, 360, 12), alpha=0.75, color="#d73027",
        edgecolor="white", linewidth=0.4, label="实例 001–030")
ax.hist(w_batchB, bins=np.arange(100, 360, 12), alpha=0.7, color="#1a9850",
        edgecolor="white", linewidth=0.4, label="实例 031–050")
ax.set_xlabel("时间窗长度 $D_j$ / s")
ax.set_ylabel("火点数量")
ax.set_title("(c) 灭火时间窗长度分布（两批数据）", fontsize=8.5)
ax.legend(fontsize=7)
ax.grid(alpha=0.2, axis="y", linestyle=":")

ax = axes[1][1]
ax.scatter(ws_all, w_all, s=2.5, alpha=0.35, color="#4575b4")
ax.set_xlabel("时间窗起点 / s")
ax.set_ylabel("时间窗长度 / s")
ax.set_title("(d) 时间窗起点与长度散点", fontsize=8.5)
ax.grid(alpha=0.2, linestyle=":")
fig.tight_layout()
fig.savefig(FIG / "fig2_params.png")
plt.close(fig)
print("fig2 done")

# ------------------------------------------------- Fig 3 time windows of inst.1
fig, ax = plt.subplots(figsize=(6.3, 4.0))
order = sorted(fps, key=lambda f: f["ws"])
colors = {1: "#74add1", 2: "#fdae61", 3: "#d73027"}
for row, f in enumerate(order):
    ax.barh(row, f["we"] - f["ws"], left=f["ws"], height=0.62,
            color=colors[f["hp"]], edgecolor="k", linewidth=0.35)
    ax.text(f["we"] + 6, row, f"V={f['value']:.0f}", va="center", fontsize=6)
ax.set_yticks(range(len(order)))
ax.set_yticklabels([f"火点{f['id']}" for f in order], fontsize=6.2)
ax.invert_yaxis()
ax.set_xlabel("时间 / s")
ax.set_xlim(0, 800)
ax.set_title("实例 001 各火点灭火任务时间窗（按起点排序，颜色表示火势）", fontsize=8.5)
handles = [plt.Rectangle((0, 0), 1, 1, color=colors[h], edgecolor="k") for h in (1, 2, 3)]
ax.legend(handles, ["HP=1", "HP=2", "HP=3"], fontsize=7, loc="lower right")
ax.grid(alpha=0.2, axis="x", linestyle=":")
fig.savefig(FIG / "fig3_windows.png")
plt.close(fig)
print("fig3 done")

# ------------------------------------------------------ Fig 4 solution schedule
log = smoke["execution_log"]
tnames = {1: "侦察", 2: "灭火", 3: "复检"}
tcolors = {1: "#1f77b4", 2: "#d62728", 3: "#2ca02c"}
tmarkers = {1: "o", 2: "s", 3: "^"}

fig, axes = plt.subplots(1, 2, figsize=(6.6, 4.3),
                         gridspec_kw={"width_ratios": [1.15, 1.0]})
ax = axes[0]
for t in (1, 2, 3):
    xs = [e["start_time"] for e in log if e["type"] == t]
    ys = [e["uav"] for e in log if e["type"] == t]
    ax.scatter(xs, ys, s=13, marker=tmarkers[t], c=tcolors[t], label=tnames[t],
               edgecolors="k", linewidths=0.25, zorder=3)
ax.set_yticks(range(1, 17))
ax.set_yticklabels([f"UAV{i}" for i in range(1, 17)], fontsize=6)
ax.set_xlabel("任务开始时刻 / s")
ax.set_title("(a) 各无人机任务时刻", fontsize=8.5)
ax.legend(fontsize=7, loc="upper left")
ax.grid(alpha=0.2, linestyle=":")
ax.set_xlim(-15, smoke["makespan"] + 25)

ax = axes[1]
for t in (1, 2, 3):
    xs = [e["start_time"] for e in log if e["type"] == t]
    ys = [e["fire_id"] for e in log if e["type"] == t]
    ax.scatter(xs, ys, s=13, marker=tmarkers[t], c=tcolors[t],
               edgecolors="k", linewidths=0.25)
for fid in range(1, 26):
    ts = sorted(e["start_time"] for e in log if e["fire_id"] == fid)
    if len(ts) == 3:
        ax.plot([ts[0], ts[2]], [fid, fid], color="gray", linewidth=0.6, zorder=1)
ax.set_yticks(range(1, 26, 2))
ax.set_yticklabels([f"火点{i}" for i in range(1, 26, 2)], fontsize=6)
ax.invert_yaxis()
ax.set_xlabel("任务开始时刻 / s")
ax.set_title("(b) 各火点三段任务链", fontsize=8.5)
ax.grid(alpha=0.2, linestyle=":")
ax.set_xlim(-15, smoke["makespan"] + 25)
fig.tight_layout()
fig.savefig(FIG / "fig4_schedule.png")
plt.close(fig)
print("fig4 done")

# ------------------------------------------------------- Fig 5 convergence curve
fig, ax = plt.subplots(figsize=(6.1, 3.2))
gen = np.arange(len(smoke["generation_best"]))
ax.plot(gen, smoke["generation_best"], color="#1f77b4", linewidth=1.3)
ax.axhline(smoke["fitness"], color="r", linestyle="--", linewidth=0.9,
           label=f"最终最优适应度 {smoke['fitness']:.0f}")
ax.set_xlabel("进化代数")
ax.set_ylabel("最优适应度")
ax.set_title(f"基线遗传算法在实例 001 上的收敛曲线（{smoke['generations_completed']} 代，"
             f"{smoke['evaluations']} 次评价）", fontsize=8.5)
ax.legend(fontsize=7.5)
ax.grid(alpha=0.25, linestyle=":")
fig.savefig(FIG / "fig5_convergence.png")
plt.close(fig)
print("fig5 done")

# ---------------------------------------------------- Fig 6 mission chain sketch
fig, ax = plt.subplots(figsize=(6.3, 2.5))
ax.axis("off")


def box(x, y, w, h, text, fc, fs=8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.015,rounding_size=0.06",
                                fc=fc, ec="k", linewidth=0.8))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def arrow(x1, y1, x2, y2, text="", style="-|>", color="k", rad=0.0, fs=7, off=(0, 0.05)):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11,
                                 color=color, linewidth=0.9,
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1], text, ha="center",
                fontsize=fs, color=color)


box(0.03, 0.36, 0.17, 0.30, "火点 $j$\n状态 0：未开始", "#f0f0f0")
box(0.27, 0.36, 0.17, 0.30, "侦察任务\n(侦察机, 无弹药消耗)", "#cfe2f3")
box(0.51, 0.36, 0.17, 0.30, "灭火任务\n(灭火机, 耗弹 $HP_j$)", "#f4cccc")
box(0.75, 0.36, 0.20, 0.30, "复检任务\n(侦察机, 无弹药消耗)", "#d9ead3")
arrow(0.20, 0.51, 0.27, 0.51)
arrow(0.44, 0.51, 0.51, 0.51)
arrow(0.68, 0.51, 0.75, 0.51, "$s_j$")
ax.text(0.355, 0.715, "状态 = 1", ha="center", fontsize=7)
ax.text(0.595, 0.715, "状态 = 2", ha="center", fontsize=7)
ax.text(0.85, 0.715, "状态 = 3：结算奖励 $3V_jHP_j$", ha="center", fontsize=7)
box(0.51, 0.04, 0.17, 0.22, "基地 [25,25]\n补给 5.0 s，弹药重置为 3", "#fff2cc", fs=7)
arrow(0.595, 0.26, 0.595, 0.36, color="#b45f06")
ax.text(0.71, 0.31, "弹药不足时\n先返回基地补给", fontsize=7, color="#b45f06",
        ha="left", va="center")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
fig.savefig(FIG / "fig6_chain.png")
plt.close(fig)
print("fig6 done")
print("figures in", FIG)

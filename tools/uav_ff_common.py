# -*- coding: utf-8 -*-
"""UAV 森林灭火 — ReEvo / EoH 适配层共用工具。

生成式框架（ReEvo、EoH）只负责产出一个“选下一个火点”的启发式函数：

    def select_next_fire(remaining_fires, fire_info, uav_state,
                         base_pos, current_time, scheduled) -> int

本模块提供固定的解码器（火点顺序 → 侦察/灭火/复检任务链 + 就近弹药感知的
UAV 贪心分配），并用权威的 EnvScheduler 计算适应度，保证与 KARES 评测口径一致。
"""
import importlib.util
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_SCHEDULER_PATH = os.path.join(ROOT, "problems", "uav_firefighting", "env_scheduler.py")
INSTANCES_DIR = os.path.join(ROOT, "instances", "uav")
BASE_POS = (25.0, 25.0)

_ENV_CLS = None


def env_scheduler_class():
    """加载固定环境调度器（不修改、不复制评分口径）。"""
    global _ENV_CLS
    if _ENV_CLS is None:
        spec = importlib.util.spec_from_file_location("__uav_env_scheduler__", ENV_SCHEDULER_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ENV_CLS = mod.EnvScheduler
    return _ENV_CLS


def load_instance(instance_path):
    with open(instance_path, "r", encoding="utf-8") as f:
        return json.load(f)


def instance_paths(scales=(25, 10, 50)):
    """按 25f 001-030、10f 001-030、50f 001-030 的顺序返回 90 条实例路径。"""
    paths = []
    for scale in scales:
        sub = os.path.join(INSTANCES_DIR, "%df" % scale)
        if scale == 25:
            names = ["firefighting_instance_%03d.json" % i for i in range(1, 31)]
        else:
            names = ["firefighting_instance_%df_%03d.json" % (scale, i) for i in range(1, 31)]
        paths.extend(os.path.join(sub, n) for n in names)
    return paths


def instance_for_scale(scale):
    """按规模挑选训练实例（默认 25 火点 001）。"""
    if os.environ.get("UAV_FF_INSTANCE"):
        return os.environ["UAV_FF_INSTANCE"]
    sub = os.path.join(INSTANCES_DIR, "%df" % scale)
    name = "firefighting_instance_001.json" if scale == 25 else "firefighting_instance_%df_001.json" % scale
    return os.path.join(sub, name)


def build_fire_info(data):
    info = {}
    for fp in data["fire_points"]:
        pos = (float(fp["pos"][0]), float(fp["pos"][1]))
        info[fp["id"]] = {
            "pos": pos,
            "value": float(fp["value0"]),
            "hp": int(fp["hp"]),
            "window_open": fp.get("window_start"),
            "window_end": fp.get("window_end"),
            "distance_from_base": math.hypot(pos[0] - BASE_POS[0], pos[1] - BASE_POS[1]),
        }
    return info


def build_fire_tasks(data):
    fire_tasks = {}
    for task in data["tasks"]:
        fire_tasks.setdefault(task["fire_id"], {})[task["type"]] = task
    return fire_tasks


def initial_uav_state(data):
    state = {}
    for u in data["uavs"]:
        state[u["id"]] = {
            "type": u["type"],
            "pos": (float(u["pos"][0]), float(u["pos"][1])),
            "ammo": int(u["ammo"]),
            "distance_used": 0.0,
            "time": 0.0,
            "max_range": float(u["max_range"]),
            "speed": float(u["speed"]),
            "base": BASE_POS,
        }
    return state


def _candidate_uavs(task_type, data):
    kind = "scout" if task_type in (1, 3) else "fighter"
    return [u["id"] for u in data["uavs"] if u["type"] == kind]


def _exec_uav(task, state, data):
    """就近 + 弹药感知贪心：为单个任务选一台 UAV，并推进该 UAV 的状态。"""
    task_type = task["type"]
    task_pos = (float(task["pos"][0]), float(task["pos"][1]))
    fire_id = task["fire_id"]
    task_hp = int(task.get("hp", 0))

    best_uid, best_score = None, float("inf")
    for uid in _candidate_uavs(task_type, data):
        u = state[uid]
        d = math.hypot(task_pos[0] - u["pos"][0], task_pos[1] - u["pos"][1])
        needs_refill = task_type == 2 and u["ammo"] < task_hp
        if needs_refill:
            to_base = math.hypot(u["base"][0] - u["pos"][0], u["base"][1] - u["pos"][1])
            from_base = math.hypot(task_pos[0] - u["base"][0], task_pos[1] - u["base"][1])
            total = to_base + from_base
        else:
            total = d
        if u["distance_used"] + total > u["max_range"]:
            continue
        score = total + (20.0 if needs_refill else 0.0)
        if score < best_score:
            best_uid, best_score = uid, score

    if best_uid is None:
        best_uid = _candidate_uavs(task_type, data)[0]

    u = state[best_uid]
    if task_type == 2 and u["ammo"] < task_hp:
        to_base = math.hypot(u["base"][0] - u["pos"][0], u["base"][1] - u["pos"][1])
        from_base = math.hypot(task_pos[0] - u["base"][0], task_pos[1] - u["base"][1])
        u["distance_used"] += to_base + from_base
        u["time"] += (to_base + from_base) / max(u["speed"], 1e-9) + 5.0
        u["pos"] = task_pos
        u["ammo"] = 3 - task_hp
    else:
        dist = math.hypot(task_pos[0] - u["pos"][0], task_pos[1] - u["pos"][1])
        u["distance_used"] += dist
        u["time"] += dist / max(u["speed"], 1e-9)
        u["pos"] = task_pos
        if task_type == 2:
            u["ammo"] -= task_hp
    return best_uid


def _fallback_fire(remaining, fire_info):
    """启发式失效时的兜底：离基地最近的火点。"""
    return min(remaining, key=lambda f: fire_info[f]["distance_from_base"])


def build_schedule(data, select_fn, strict=True):
    """用给定的“下一火点”启发式构造 (task_order, uav_assignment)。"""
    fire_info = build_fire_info(data)
    fire_tasks = build_fire_tasks(data)
    state = initial_uav_state(data)

    remaining = sorted(fire_info.keys())
    scheduled = []
    task_order, uav_assignment = [], []
    fallbacks = 0

    while remaining:
        snapshot = dict((uid, dict(v)) for uid, v in state.items())
        current_time = max(u["time"] for u in state.values())
        try:
            nxt = select_fn(list(remaining), fire_info, snapshot, BASE_POS,
                            current_time, list(scheduled))
        except Exception:
            if strict:
                raise
            nxt = _fallback_fire(remaining, fire_info)

        if not isinstance(nxt, int) or isinstance(nxt, bool):
            try:
                nxt = int(nxt)
            except (TypeError, ValueError):
                if strict:
                    raise ValueError("select_next_fire returned a non-integer: %r" % (nxt,))
                nxt = None
        if nxt not in remaining:
            if strict:
                raise ValueError("select_next_fire returned %r, not in remaining %s"
                                 % (nxt, remaining[:10]))
            nxt = _fallback_fire(remaining, fire_info)
            fallbacks += 1

        for task_type in (1, 2, 3):
            task = fire_tasks[nxt][task_type]
            uav_assignment.append(_exec_uav(task, state, data))
            task_order.append(task["id"])
        remaining.remove(nxt)
        scheduled.append(nxt)

    return task_order, uav_assignment, fallbacks


def evaluate_schedule(data, instance_path, select_fn, strict=True):
    task_order, uav_assignment, fallbacks = build_schedule(data, select_fn, strict=strict)
    result = env_scheduler_class()(data_file=instance_path).simulate_decoded(task_order, uav_assignment)
    result["fallbacks"] = fallbacks
    return result


def evaluate_many(paths, select_fn, strict=False):
    """对多条实例逐一评估，返回结果列表。"""
    results = []
    for path in paths:
        data = load_instance(path)
        try:
            res = evaluate_schedule(data, path, select_fn, strict=strict)
            res["instance"] = os.path.basename(path)
            res["error"] = None
        except Exception as exc:  # 单条失败不影响其余实例
            res = {"instance": os.path.basename(path), "fitness": None, "error": repr(exc)}
        res.pop("execution_log", None)
        results.append(res)
    return results

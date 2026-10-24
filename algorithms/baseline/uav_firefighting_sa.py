"""Simulated annealing baseline for the UAV firefighting scheduling problem.

Interface matches the workflow contract:
    __init__(self, scheduler, **kwargs)
    run(self, verbose=False) -> dict

The evaluator pins pop_size x generations to 600 x 150 = 90000 fitness
evaluations. This baseline spends exactly that budget: one evaluation per
annealing iteration, no population, no crossover.

Calibration (seed 42, 90000 evaluations, example instances, measured):
    instance 001: SOGA 6538 | this SA 4595
    instance 002: SOGA 2467 | this SA 4242
    instance 003: SOGA 4792 | this SA 5027
    mean:         SOGA 4599 | this SA 4621
The neighborhood is deliberately minimal (single swap on task_order, no
assignment moves, no constraint repair, no reheating): keeping the baseline
at SOGA's level on average rather than saturating the objective, so
improvements from generated candidates remain measurable.

Encoding: chromosome = task_order (length num_tasks) + uav_assignment
(length num_tasks), decoded through scheduler.simulate_decoded().
"""

import json
import math
import os
import random


class SAOptimizer:
    """Minimal simulated annealing: random feasible start, swap neighborhood."""

    def __init__(self, scheduler, **kwargs):
        self.scheduler = scheduler
        self.pop_size = kwargs.get("pop_size", 600)
        self.generations = kwargs.get("generations", 150)
        # 评估预算：与 SOGA 的 pop_size * generations 对齐 = 90000
        self.total_budget = int(kwargs.get("eval_budget",
                                           self.pop_size * self.generations))

        # 温度参数（相对初始解的量级自适应）
        self.t0_ratio = kwargs.get("t0_ratio", 0.02)
        self.t_end_ratio = kwargs.get("t_end_ratio", 1e-4)

        self.num_tasks = scheduler.num_tasks
        self.task_ids = list(range(1, self.num_tasks + 1))
        self.scout_uavs = scheduler.scout_uavs
        self.fighter_uavs = scheduler.fighter_uavs

        # 任务 -> 前置任务（scout -> fire -> recheck 链），仅用于构造可行初始解
        self.prereq = {}
        for _fid, tasks in scheduler.fire_tasks.items():
            if 1 in tasks and 2 in tasks:
                self.prereq[tasks[2] + 1] = tasks[1] + 1
            if 2 in tasks and 3 in tasks:
                self.prereq[tasks[3] + 1] = tasks[2] + 1

    # ------------------------------------------------------------------
    # 解构造
    # ------------------------------------------------------------------
    def _initial_solution(self):
        """随机生成一个满足前置约束的顺序 + 类型匹配的分配。"""
        remaining = list(self.task_ids)
        placed = set()
        order = []
        while remaining:
            ready = [t for t in remaining
                     if self.prereq.get(t) is None or self.prereq[t] in placed]
            if not ready:
                ready = remaining
            t = random.choice(ready)
            order.append(t)
            placed.add(t)
            remaining.remove(t)

        assign = []
        for t in order:
            task = self.scheduler.tasks[t - 1]
            pool = self.fighter_uavs if task["type"] == 2 else self.scout_uavs
            assign.append(random.choice(pool))
        return order, assign

    # ------------------------------------------------------------------
    # 邻域：只交换任务顺序，分配保持不变
    # ------------------------------------------------------------------
    def _neighbor(self, order):
        n = self.num_tasks
        i, j = random.sample(range(n), 2)
        new_order = order[:]
        new_order[i], new_order[j] = new_order[j], new_order[i]
        return new_order

    # ------------------------------------------------------------------
    # 评估
    # ------------------------------------------------------------------
    def _evaluate(self, order, assign):
        result = self.scheduler.simulate_decoded(order, assign)
        return result["fitness"], result

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def run(self, verbose=False):
        order, assign = self._initial_solution()
        best_fitness, best_result = self._evaluate(order, assign)
        evals = 1

        best_order = order[:]
        cur_order = order
        cur_fitness = best_fitness

        f_scale = max(abs(best_fitness), 1.0)
        t0 = self.t0_ratio * f_scale
        t_end = self.t_end_ratio * f_scale
        iterations = max(self.total_budget - 1, 1)
        cool_rate = (t_end / t0) ** (1.0 / iterations)
        temperature = t0
        accepted = 0

        if verbose:
            print(f"{'Eval':>8} | {'Cur':>12} | {'Best':>12} | {'T':>10} | {'Acc':>8}")
            print("-" * 62)

        while evals < self.total_budget:
            new_order = self._neighbor(cur_order)
            new_fitness, new_result = self._evaluate(new_order, assign)
            evals += 1

            delta = new_fitness - cur_fitness
            if delta >= 0.0 or random.random() < math.exp(delta / max(temperature, 1e-12)):
                cur_order, cur_fitness = new_order, new_fitness
                accepted += 1
                if new_fitness > best_fitness + 1e-9:
                    best_fitness = new_fitness
                    best_result = new_result
                    best_order = new_order[:]

            temperature *= cool_rate

            if verbose and evals % max(self.total_budget // 10, 1) == 0:
                print(f"{evals:>8} | {cur_fitness:>12.2f} | {best_fitness:>12.2f} | "
                      f"{temperature:>10.4f} | {accepted:>8}")

        if verbose:
            print(f"\nBest fitness: {best_fitness:.2f}")
            print(f"Evaluations: {evals}")

        return {
            "best_fitness": best_fitness,
            "best_result": best_result,
            "best_individual": best_order + assign,
            "evaluation_count": evals,
            # SA 没有“代”的概念；这里固定为单个退火过程
            "generations_completed": 1,
        }


if __name__ == "__main__":
    import importlib.util

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(root, "problems", "uav_firefighting", "env_scheduler.py")
    inst_path = os.path.join(root, "instances", "firefighting_instance",
                             "example", "firefighting_instance_001.json")

    spec = importlib.util.spec_from_file_location("__env_scheduler__", env_path)
    env_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(env_mod)
    scheduler = env_mod.EnvScheduler(data_file=inst_path, random_seed=42)

    sa = SAOptimizer(scheduler, pop_size=600, generations=150)
    result = sa.run(verbose=True)
    print(json.dumps({k: result[k] for k in
                      ("best_fitness", "evaluation_count", "generations_completed")},
                     ensure_ascii=False, indent=2))

# -*- coding: utf-8 -*-
"""Run the authoritative baseline GA (algorithms/baseline/uav_firefighting_soga.py)
on selected instances and record solution quality + convergence history.

Usage: python solve.py <out.json> [iid:seed ...]
"""
import importlib.util
import json
import sys
import time
from pathlib import Path

BASE = Path(r"C:\kares_main\algorithms\baseline\uav_firefighting_soga.py")
EX = Path(r"C:\kares_main\instances\firefighting_instance\example")
BUILD = Path(__file__).resolve().parent


def load_baseline():
    spec = importlib.util.spec_from_file_location("baseline_soga", BASE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_one(mod, iid, seed, pop_size=600, generations=150, patience=80):
    import random
    random.seed(seed)
    scheduler = mod.SingleObjectiveScheduler(
        data_file=str(EX / f"firefighting_instance_{iid:03d}.json"), random_seed=seed
    )
    ga = mod.SimpleGA(scheduler, pop_size=pop_size, generations=generations, patience=patience)
    history = []
    orig_eval = ga.evaluate

    def logged(ind):
        fit, res = orig_eval(ind)
        history.append(fit)
        return fit, res

    ga.evaluate = logged
    t0 = time.perf_counter()
    out = ga.run(verbose=False)
    elapsed = time.perf_counter() - t0

    # best fitness of each generation (initial population = generation 0)
    gens = [max(history[i:i + pop_size]) for i in range(0, len(history), pop_size)]
    best = out["best_result"]
    executed = [e for e in best["execution_log"] if e["status"] == "executed"]
    skipped = [e for e in best["execution_log"] if e["status"] != "executed"]
    return {
        "instance_id": iid,
        "seed": seed,
        "fitness": round(out["best_fitness"], 4),
        "net_reward": round(best["net_reward"], 4),
        "completed_fires": best["completed_fires"],
        "makespan": round(best["makespan"], 4),
        "constraint_violation": round(best["constraint_violation"], 4),
        "executed_tasks": len(executed),
        "skipped_tasks": len(skipped),
        "evaluations": out["evaluation_count"],
        "generations_completed": out["generations_completed"],
        "seconds": round(elapsed, 2),
        "generation_best": [round(g, 4) for g in gens],
        "execution_log": executed,
        "skipped_log": skipped,
        "chromosome_order": out["best_individual"][:75],
        "chromosome_assign": out["best_individual"][75:],
    }


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BUILD / "solve_results.json"
    jobs = []
    for arg in sys.argv[2:]:
        iid, seed = arg.split(":")
        jobs.append((int(iid), int(seed)))
    if not jobs:
        jobs = [(i, 42) for i in (1, 10, 20, 31, 40, 50)]

    mod = load_baseline()
    results = []
    for iid, seed in jobs:
        r = run_one(mod, iid, seed)
        print(f"iid={iid} seed={seed} fit={r['fitness']:.2f} fires={r['completed_fires']} "
              f"cv={r['constraint_violation']} makespan={r['makespan']:.1f} t={r['seconds']}s",
              flush=True)
        results.append(r)
        out_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    print("written:", out_path)


if __name__ == "__main__":
    main()

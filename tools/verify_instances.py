"""Verify instance loading and baseline runnability for the four CVRP sets."""
import os
import sys
import importlib.util

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from kares_workflow.problem_loader import ProblemLoader

SETS = ["cvrp_set_e", "cvrp_set_f", "cvrp_set_m", "cvrp_set_p"]
BASELINE_DIR = os.path.join(PROJECT_ROOT, "algorithms", "baseline")


def load_baseline_module(set_name):
    """Dynamically load a baseline module; returns (scheduler_cls, ga_cls)."""
    path = os.path.join(BASELINE_DIR, f"{set_name}_soga.py")
    spec = importlib.util.spec_from_file_location(f"{set_name}_soga", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # find the Scheduler class and the GA class
    sched_cls = None
    ga_cls = None
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type):
            if "Scheduler" in name:
                sched_cls = obj
            elif any(k in name for k in ("GA", "Algorithm", "Optimizer", "PSO", "SA", "DE", "Search")):
                ga_cls = obj
    return sched_cls, ga_cls, mod


def main():
    total = 0
    for s in SETS:
        print(f"\n=== {s} ===")
        pl = ProblemLoader(s)
        insts = pl.get_instances()
        print(f"  found {len(insts)} instances")
        print(f"  instances_dir = {pl.instances_dir}")
        print(f"  instance_pattern = {pl.instance_pattern}")
        print(f"  baseline_path = {os.path.basename(pl.baseline_path)}")
        if insts:
            print(f"  first instance = {os.path.basename(insts[0])}")
            print(f"  last instance = {os.path.basename(insts[-1])}")

        # verify the baseline can load the first instance
        sched_cls, ga_cls, _ = load_baseline_module(s)
        if sched_cls is None or ga_cls is None:
            print(f"  [ERROR] baseline missing classes: Scheduler={sched_cls}, GA={ga_cls}")
            continue
        sched = sched_cls(data_file=insts[0], random_seed=42)
        print(f"  Scheduler loaded: dim={sched.dimension}, cap={sched.capacity}, "
              f"customers={sched.num_customers}")

        # quick minimal GA run (smallest instance only)
        ga = ga_cls(sched, pop_size=20, generations=5)
        res = ga.run(verbose=False)
        br = res["best_result"]
        print(f"  GA smoke test: best_fitness={res['best_fitness']:.1f}, "
              f"distance={br.get('total_distance', '?')}, "
              f"vehicles={br.get('num_vehicles', '?')}, evals={res['evaluation_count']}")
        total += len(insts)
    print(f"\n=== Total instances: {total} ===")


if __name__ == "__main__":
    main()

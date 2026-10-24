"""Smoke-test the CVRP baselines through the pipeline evaluator to verify
interface compatibility."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kares_workflow.evaluator import _run_one, evaluate_algorithm
from kares_workflow.problem_loader import ProblemLoader

SETS = ["cvrp_set_e", "cvrp_set_f", "cvrp_set_m", "cvrp_set_p"]

for s in SETS:
    print(f"\n=== {s} end-to-end evaluation ===")
    pl = ProblemLoader(s)
    insts = pl.get_instances(limit=2)  # first 2 only for a quick smoke test
    print(f"  instances: {[os.path.basename(i) for i in insts]}")

    # single instance via _run_one
    if insts:
        result = _run_one(pl.baseline_path, insts[0], seed=42, timeout=60)
        print(f"  _run_one: ok={result.get('ok')}, "
              f"best_fitness={result.get('best_fitness')}, "
              f"error={(result.get('error') or '')[:120]}")

    # multi-instance via evaluate_algorithm
    if len(insts) >= 2:
        ev = evaluate_algorithm(pl.baseline_path, insts[:2], seed=42, timeout_per_inst=60)
        print(f"  evaluate_algorithm: ok={ev.get('ok')}, "
              f"mean_fitness={ev.get('mean_fitness')}, "
              f"completed={ev.get('completed')}/{ev.get('total')}, "
              f"std={ev.get('std_fitness')}")

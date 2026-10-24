# algorithms/baseline

**Baseline algorithm seeds** for the KARES workflow. Each problem has a
corresponding `<problem>_soga.py` (Single-Objective GA), which serves as the
initial `AlgorithmPool.seed` when `KARESOrchestrator` starts and provides the
base for subsequent diff/base generators to improve upon incrementally.

## File Manifest

| File | Problem | Chromosome / Decoding | Objective | Proxy fitness convention |
|------|---------|----------------------|-----------|--------------------------|
| [cvrp_set_e_soga.py](cvrp_set_e_soga.py) | CVRPLib Set E | Customer permutation + greedy split | Minimize total travel distance | `fitness_large - total_distance` (adaptive to instance scale, guaranteed positive) |
| [cvrp_set_f_soga.py](cvrp_set_f_soga.py) | CVRPLib Set F | Same as above | Same as above | Same as above |
| [cvrp_set_m_soga.py](cvrp_set_m_soga.py) | CVRPLib Set M | Same as above | Same as above | Same as above |
| [cvrp_set_p_soga.py](cvrp_set_p_soga.py) | CVRPLib Set P | Same as above | Same as above | Same as above |
| [uav_firefighting_soga.py](uav_firefighting_soga.py) | Forest firefighting UAV scheduling | UAV–fire point assignment permutation | Maximize net reward | Uses net reward directly (already maximization semantics) |

## Common Operators (GA Skeleton)

- Crossover: OX (order crossover)
- Mutation: swap / inversion / insert
- Selection: tournament + elitism
- **Deliberately excludes 2-opt and other local search**: this is left for the
  LLM to introduce autonomously during the workflow as an improvement direction.

## Interface Contract

- Scheduler class `__init__(self, data_file, random_seed=None)`: loads the instance JSON.
- Algorithm class `__init__(self, scheduler, ...)`: runs the GA with the injected scheduler.
- Candidates must expose `best_fitness` / `best_solution` for `evaluator.evaluate_algorithm`.
- See `problems/<problem>/interface_contract.md` and `INTERFACE_CONTRACT` in
  `kares_workflow/config.py` for the detailed contract.

## Notes

- The proxy fitness maps "minimization problems" onto the pipeline-wide
  "maximization" semantics, so that `AlgorithmPool`, `label_stats`, and the
  `vi` value computation never need to be aware of the problem direction.
- `fitness_large` is an upper-bound estimate; the constant cancels out in
  relative improvements (`child - parent`) and does not affect label/vi signals.

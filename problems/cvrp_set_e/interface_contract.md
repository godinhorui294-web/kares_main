# CVRP Algorithm Interface Contract (CVRPLib Set E)

The generated algorithm code must be a complete, directly runnable Python file that obeys the following contract:

## 1. Scheduler Class (class name contains Scheduler)
```python
__init__(self, data_file: str, random_seed: int = None)
```
- Loads the instance from `data_file` (JSON), with fields:
  - `dimension`: total number of nodes (depot included)
  - `num_customers`: number of customers = dimension - 1
  - `capacity`: vehicle capacity Q
  - `depot_id`: depot node id (always 1)
  - `edge_weight_type`: `EUC_2D` (most instances; Euclidean distance, rounded) or `EXPLICIT` (a few instances; use distance_matrix directly)
  - `nodes`: `[{id, x, y, demand, is_depot}]`, with the depot marked `is_depot=true`
  - `distance_matrix`: n×n integer distance matrix, index = id-1 (**look it up directly; do not recompute distances from coordinates**)
  - `optimal`: best known value published by CVRPLib (for reporting the gap only; **the algorithm must not read it during solving**)

```python
simulate(self, chromosome: list) -> dict
```
- `chromosome` is a full permutation of customer ids (depot excluded, 1-indexed), length = num_customers
- The returned dict must contain at least:
  - `fitness: float` — proxy fitness = **self.fitness_large - total_distance** (larger is better); `self.fitness_large` is computed adaptively for the instance in __init__
  - `total_distance: float` — the true total distance (for reporting; distance = self.fitness_large - fitness)
  - `routes: list` — the decoded route list (each route is a sequence of customer ids)
  - `num_vehicles: int` — number of routes
  - `feasible: bool`

## 2. Algorithm Class (class name contains one of GA / Algorithm / Optimizer / Search / DE / SA / PSO)
```python
__init__(self, scheduler, **kwargs)
run(self, verbose: bool = False) -> dict
```
- `run()` returns a dict containing at least:
  - `best_fitness: float`
  - `best_result: dict` (with total_distance / routes / num_vehicles / feasible)
  - `best_individual: list` (best chromosome)
  - `evaluation_count: int`
  - `generations_completed: int`

## 3. Fitness Semantics (Key)
- CVRP is a **minimization** problem, but the pipeline compares by "maximization" end to end (sorting / improvement detection / barrier floor / label / vi)
- Hence `best_fitness = self.fitness_large - total_distance`, where:
  ```python
  # In __init__: guarantee fitness_large > the total distance of any feasible solution
  max_edge = max(max(r) for r in self.distance_matrix)
  self.fitness_large = max(3000, 2 * self.dimension * max_edge)
  ```
  - The worst feasible solution has at most 2*(dim-1) edges, each ≤ max_edge, so 2*dim*max_edge is a safe upper bound
  - The adaptive form prevents negative fitness on large instances (n≥100) where distances exceed a fixed constant
  - Smaller distance → larger fitness → better
  - The constant 3000 cancels out in relative improvements (fitness_c - fitness_p), keeping the label/vi signals meaningful
- **Infeasible solutions** (capacity exceeded / wrong chromosome length / duplicated or missing customers) must return `fitness = 0` (far below the proxy value of any feasible solution; filtered by the barrier floor)
- `best_result` must contain the `total_distance` field so that reports can recover the true distance

## 4. Miscellaneous
- Use only the Python standard library and numpy (optional); no other external packages
- No undefined variables / unimported modules
- The file header comment must state: the algorithm name, the Borrowed knowledge sources, and the core innovation of this generation

See `algorithms/baseline/cvrp_set_e_soga.py` for a reference implementation (CVRPScheduler + CVRPGA, greedy split + OX crossover).

# instances

**Test instances** for each KARES problem. `ProblemLoader` locates instance files
in this directory via the `instance_pattern` field of `problem_definition.json`,
and `evaluator.evaluate_algorithm` runs them in subprocesses.

## Directory Layout

```
instances/
├── cvrp_set_e/      # CVRPLib Set E (13 instances)
├── cvrp_set_f/      # CVRPLib Set F (3 instances)
├── cvrp_set_m/      # CVRPLib Set M (5 instances)
├── cvrp_set_p/      # CVRPLib Set P (24 instances)
├── uav/             # forest firefighting UAV instances (30 per scale tier)
│   ├── 25f/firefighting_instance_001~030.json  # 25 fire points, 16 UAVs
│   ├── 10f/firefighting_instance_10f_001~030.json # 10 fire points, 8 UAVs
│   └── 50f/firefighting_instance_50f_001~030.json # 50 fire points, 32 UAVs
├── tsp20_instance_001~050.json          # TSP-20 instances (50)
├── tsp50_instance_001~050.json          # TSP-50 instances (50)
├── eil51.json / kroA100.json / ts225.json   # standard TSPLIB benchmarks
```

## CVRP Subset Naming

CVRPLib standard naming `<type>-n<nodes>-k<vehicles>.json`:

- **E / F / M / P**: the four classic CVRP benchmark sets — Christofides-Eilon / Fisher / Christofides-Mingozzi-Toth / Augerat — covering different scales and topological characteristics, useful for assessing algorithm generalization.
- `n`: total node count (customers + depot).
- `k`: number of available vehicles.

## Instance Format

Each JSON file is parsed by `Scheduler.__init__` in the corresponding
`algorithms/baseline/<problem>_soga.py`. Common field examples:

- `depot` / `nodes` / `demands` / `capacity`: CVRP
- `uavs` / `fires` / `base`: UAV firefighting instances

To switch problems or add instances, simply drop the instances into the
corresponding subdirectory and adjust `instance_pattern` in
`problems/<problem>/problem_definition.json` — no changes inside `kares_workflow/`
are required.

# CVRP Constraint List

## Hard Constraints (must hold; otherwise the solution is infeasible → fitness=0)
- C1 Capacity: the sum of customer demands on each route ≤ capacity(Q)
- C2 Depot start/end: every route must depart from and return to the depot
- C3 Full customer coverage: each customer is visited exactly once by exactly one vehicle (the chromosome is a permutation of customer ids, which structurally guarantees no duplicates and no omissions)
- C4 Single depot: all vehicles share the same depot (id=1)

## Soft Constraints
- None (the standard CVRP definition has no soft constraints; exceeding capacity is judged directly infeasible)

## Infeasibility Handling
- Any route exceeding capacity → the solution gets `fitness = 0`
- Chromosome length ≠ number of customers → `fitness = 0`
- Chromosome containing duplicated/missing customers → `fitness = 0`

## Fleet Size
- Not fixed: the number of vehicles is determined automatically by the capacity and the customer permutation (the number of routes after greedy split is the fleet size)
- The k in instance names (e.g., F-n72-k4) is the nominal CVRPLib vehicle count, for reference only; the algorithm need not match k exactly — fewer routes with a shorter total distance suffices

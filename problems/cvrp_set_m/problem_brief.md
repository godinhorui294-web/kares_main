# CVRPLib Set M — Capacitated Vehicle Routing Problem (CVRP)

## Problem Overview
Given a single depot, a set of customers (each with a demand), and a vehicle capacity Q, all customers must be served by a fleet of vehicles: every route starts and ends at the depot, the sum of demands along each route must not exceed Q, and the objective is to minimize the total travel distance.

## Distance
EUC_2D: node coordinates are 2D points and distance = round(√(dx²+dy²)). The instance JSON ships a precomputed `distance_matrix`; algorithms should look it up directly rather than recomputing distances from coordinates.

## Encoding and Decoding
Chromosome = a full permutation of customer ids (depot excluded, 1-indexed). Decoding uses a greedy split: accumulate demands in permutation order, and open a new route once the accumulated load would exceed the capacity. The fleet size is determined automatically by the capacity and the permutation (k is not fixed).

## Objective and Fitness Convention (Key)
- Objective: **minimize** total_distance (CVRP is a minimization problem)
- Proxy fitness: `best_fitness = 3000 - total_distance` (the pipeline compares by "maximization" end to end, so the minimization objective is mapped onto maximization semantics; the constant 3000 cancels out in relative improvements, keeping the label/vi signals meaningful)
- Smaller distance → larger fitness → better
- Infeasible solutions (capacity exceeded / not all customers visited) must return `fitness = 0` (far below the proxy value of any feasible solution)

## Scale
Set M: only 1 instance (M-n101-k10, n=101), with an optimum around 820. The pipeline still runs on a single instance (fast evaluation takes min(3,1)=1, and the std check is skipped automatically for a single instance); the set is best suited for generalization validation rather than as the main iteration target.

## Improvement Directions (for reflection reference)
- Intra-route 2-opt local search (absent from the baseline; the main improvement opportunity)
- Inter-route exchange/relocate moves (inter-route move / cross-exchange)
- Split decoding upgrade (Prins optimal split, O(n²))
- Population diversity maintenance (aging, restarts, adaptive mutation rates)

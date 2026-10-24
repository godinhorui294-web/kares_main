# Problem Brief: Forest Firefighting UAV Mission Planning (UAV-Firefighting)

## Scenario

Multiple fires break out across a forest region. The ground command center operates a heterogeneous UAV fleet (4 scout UAVs + 12 fighter UAVs). Each fire point requires three sequential tasks: **reconnaissance → firefighting → reinspection**. A fire point counts as fully extinguished — and yields its protection value reward — only when all three tasks complete successfully.

- Reconnaissance/reinspection tasks: no time windows, executed by scout UAVs, no ammunition consumed.
- Firefighting task: subject to a **time window constraint**, executed by a fighter UAV, consuming ammunition equal to the fire point's HP `HP_j` (1/2/3).
- A fighter UAV that runs out of ammunition may return to the base `[25,25,10]` to refill (5.0 seconds; ammunition resets to 3 after refilling).
- All UAVs cruise at a constant speed of 0.5 km/s and are limited by a maximum flight range (1000 km for scouts, 800 km for fighters).

## Scale

- 25 fire points, 3 tasks each, 75 tasks in total.
- The chromosome uses a **two-layer encoding** of length 150: the first 75 genes are a task permutation (a full permutation of 1~75 denoting execution order), and the last 75 genes are the UAV assignment (one-to-one with the tasks, values in 1~16).

## Objective Function (maximize net reward)

```
F = total reward − delay cost − flight cost − constraint violation penalty
```

- **Total reward** `R = Σ 3·V_j·HP_j` (summed only over fire points with all three tasks completed; `V_j` is the protection value, 50~100)
- **Delay cost** `C_delay = Σ max(0, start_j − end_j)·10` (linear penalty for firefighting tasks starting past the time window `end_j`)
- **Flight cost** `C_fly = (Σ accumulated flight range over all UAVs)·3`
- **Constraint violation penalty** `P = N_violation·1000`

## Encoding and Decoding Essentials

- Task IDs: the three tasks of fire point `j` are `(j-1)*3+1` (reconnaissance), `(j-1)*3+2` (firefighting), and `(j-1)*3+3` (reinspection).
- Decoding: process tasks in chromosome order, taking the UAV assignment from the second half; check the sequence constraint, UAV type match, and ammunition/flight range feasibility in turn. Firefighting tasks tolerate delay (penalized but not skipped); reconnaissance/reinspection have no time windows.
- If a fighter UAV's remaining ammunition < `HP_j`: fly to the base first to refill (ammunition resets to 3), then to the fire point; the round trip must be checked against the flight range limit.

## Instance Data Format

The instance JSON contains `instance_id / uavs / fire_points / tasks`:
- `uavs[i]`: `{id, type(scout/fighter), pos[x,y,z], speed, max_range, ammo}`
- `fire_points[j]`: `{id, pos[x,y,z], value0, hp, window_start, window_end}`
- `tasks[k]`: `{id, fire_id, type(1/2/3), pos, hp, window_start, window_end, duration}`

See `problem_definition.json` for details.

# Constraint List: UAV-Firefighting

## Hard Constraints (each violation incurs a +1000 penalty and the corresponding task fails and is skipped)

### C1. Sequential Dependency
- The three tasks of each fire point must be executed strictly in the order **reconnaissance (1) → firefighting (2) → reinspection (3)**.
- During decoding: a firefighting task requires fire point state = 1 (reconnaissance done); a reinspection task requires fire point state = 2 (firefighting done). Otherwise the task fails (sequence violation).

### C2. UAV Type Matching
- Reconnaissance tasks (type=1) and reinspection tasks (type=3): may only be assigned to **scout UAVs** (ids 1~4, type=scout).
- Firefighting tasks (type=2): may only be assigned to **fighter UAVs** (ids 5~16, type=fighter).
- A mismatch causes the task to fail.

### C3. Ammunition Constraint
- When executing a firefighting task, a fighter UAV must have **remaining ammunition ≥ HP_j** (HP_j ∈ {1,2,3}).
- If short: it must first return to the base `[25,25,10]` to refill — refilling takes 5.0 seconds and resets ammunition to 3 — and then fly to the fire point.
- Consumption: after a firefighting task, the remaining ammunition decreases by HP_j.

### C4. Flight Range Constraint
- Each UAV's accumulated flight distance must not exceed its `max_range` (1000 km for scouts, 800 km for fighters).
- Including refill round trips: it must be verified that `accumulated range + distance to base + distance from base to fire point ≤ max_range`; otherwise the task fails.
- Tasks exceeding the limit fail (penalty +0.1~1 depending on the situation) and are skipped.

## Soft Constraints / Time Windows

### T1. Firefighting Time Window
- Only firefighting tasks have a time window `[window_start, window_end]` (reconnaissance/reinspection have none).
- Arriving before `window_start`: wait until `window_start` to start (start time = window_start).
- Arriving after `window_end`: **delay is allowed** (the task is not skipped), incurring only the delay cost `max(0, start − end)·10`.

## Reward Rule

- The reward `3·V_j·HP_j` is accumulated only when all three tasks of a fire point succeed (state advances to 3 = reinspection done).
- Partial completion earns no reward.

## Decoding Procedure (Summary)

For each task `i` in the chromosome:
1. Take `assigned_uav = chromosome[75 + i]`;
2. Sequence constraint check (C1) → type matching check (C2) → ammunition/flight range check (C3/C4);
3. Compute flight distance/time and determine the start time (including refills and time-window waits, T1);
4. Update UAV state (position/time/ammunition/flight range) and fire point state;
5. On reinspection completion, accumulate the fire point's reward.

## Constants

| Constant | Value |
|------|----|
| UAV speed | 0.5 km/s |
| Flight cost coefficient | 3 /km |
| Delay penalty coefficient | 10 /unit time |
| Refill time | 5.0 s |
| Ammunition after refill | 3 |
| Base coordinates | [25, 25, 10] |
| Hard constraint violation penalty | 1000 /occurrence |
| Reward formula | 3·V_j·HP_j |

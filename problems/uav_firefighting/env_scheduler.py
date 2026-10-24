# ============================================================================
# Fixed environment scheduler (EnvScheduler) — must not be modified by
# candidate algorithms.
#
# This file defines the standard evaluation environment for the UAV
# firefighting scheduling problem:
#   - chromosome decoding rules
#   - task execution simulation
#   - fitness computation formula (reward coefficient=3, penalty coefficient=1000)
#
# Candidate algorithms may only generate the "algorithm class" (GA/PSO/ACO and
# other search strategies); they call scheduler.simulate(chromosome) to obtain
# fitness and must not modify this file.
# ============================================================================

import json
import random
import math

try:
    import numpy as np
except ImportError:
    np = None


class EnvScheduler:
    """UAV firefighting scheduling — fixed evaluation environment.

    Chromosome format: task_order(length num_tasks) + uav_assignment(length num_tasks)
    simulate(chromosome) → dict(fitness, net_reward, completed_fires, ...)
    """

    def __init__(self, data_file, random_seed=None):
        with open(data_file, 'r') as f:
            data = json.load(f)

        self.uavs = data['uavs']
        self.tasks = data['tasks']
        self.fire_points = data['fire_points']
        self.num_uavs = len(self.uavs)
        self.num_tasks = len(self.tasks)
        self.num_fire_points = len(data['fire_points'])

        self.fire_tasks = {}
        for i, task in enumerate(self.tasks):
            fid = task['fire_id']
            ttype = task['type']
            if fid not in self.fire_tasks:
                self.fire_tasks[fid] = {}
            self.fire_tasks[fid][ttype] = i

        self.scout_uavs = [u['id'] for u in self.uavs if u['type'] == 'scout']
        self.fighter_uavs = [u['id'] for u in self.uavs if u['type'] == 'fighter']
        self.task_type_to_uav_type = {1: 'scout', 2: 'fighter', 3: 'scout'}
        self.base_pos = [25, 25, 10]

        if random_seed:
            random.seed(random_seed)
            try:
                np.random.seed(random_seed)
            except (NameError, AttributeError):
                pass

    def decode_chromosome(self, chromosome):
        """Standard decoding: chromosome = task_order(first num_tasks) + uav_assignment(last num_tasks)."""
        n = self.num_tasks
        task_order = chromosome[:n]
        uav_assignment = chromosome[n:]
        return task_order, uav_assignment

    def simulate(self, chromosome):
        """Standard evaluation entry point (chromosome is the concatenated list task_order+uav_assignment).

        If an algorithm uses a custom encoding (e.g., a fire point priority permutation),
        it should first decode it into (task_order, uav_assignment) inside the algorithm
        class's evaluate() and then call simulate_decoded().
        """
        task_order, uav_assignment = self.decode_chromosome(chromosome)
        return self.simulate_decoded(task_order, uav_assignment)

    def simulate_decoded(self, task_order, uav_assignment):
        """Core simulation engine (fixed scoring rules and constraint logic).

        Args:
            task_order: list[int] — task execution order (task IDs, 1-based), length=num_tasks
            uav_assignment: list[int] — UAV ID assigned to each task, same length as task_order

        Returns:
            dict: fitness, net_reward, completed_fires, makespan, constraint_violation, ...

        Scoring formula (fixed, not modifiable):
            reward  = 3 × fire_value × fire_hp  (each time a fire point's reinspection task completes)
            fly_cost = 3 × total_distance
            delay_cost = 10 × overtime
            penalty = 1000 × constraint_violation
            fitness = reward - fly_cost - delay_cost - penalty
        """
        uav_state = {}
        base_pos = [25, 25]
        for u in self.uavs:
            uav_state[u['id']] = {
                'pos': u['pos'][:2],
                'time': 0.0,
                'ammo': u['ammo'],
                'distance': 0.0,
                'type': u['type'],
                'max_range': u['max_range'],
                'speed': u['speed'],
                'base': base_pos
            }
        fire_state = {i: 0 for i in range(1, self.num_fire_points + 1)}
        task_done = [False] * self.num_tasks
        completed_fires = set()
        total_reward = 0
        total_delay_cost = 0
        constraint_violation = 0.0
        makespan = 0.0
        fire_hp = {task['fire_id']: task['hp'] for task in self.tasks if task['type'] == 2}
        fire_value = {fp['id']: fp['value0'] for fp in self.fire_points}
        execution_log = []

        for i, task_id in enumerate(task_order):
            task_idx = task_id - 1
            task = self.tasks[task_idx]
            fire_id = task['fire_id']
            task_type = task['type']
            assigned_uav = uav_assignment[i]

            if task_type == 2 and fire_state[fire_id] != 1:
                constraint_violation += 1
                execution_log.append({
                    'task_id': task_id, 'type': task_type, 'uav': assigned_uav,
                    'status': 'skipped', 'reason': f'fire point {fire_id} not yet scouted (state={fire_state[fire_id]})'
                })
                continue
            if task_type == 3 and fire_state[fire_id] != 2:
                constraint_violation += 1
                execution_log.append({
                    'task_id': task_id, 'type': task_type, 'uav': assigned_uav,
                    'status': 'skipped', 'reason': f'fire point {fire_id} not yet extinguished (state={fire_state[fire_id]})'
                })
                continue

            required_type = self.task_type_to_uav_type[task_type]
            actual_type = uav_state[assigned_uav]['type']
            if required_type != actual_type:
                constraint_violation += 10
                execution_log.append({
                    'task_id': task_id, 'type': task_type, 'uav': assigned_uav,
                    'status': 'skipped', 'reason': f'UAV type mismatch (required {required_type}, actual {actual_type})'
                })
                continue

            candidates = [assigned_uav]
            if task_type == 2 and uav_state[assigned_uav]['ammo'] < task['hp']:
                dist_to_base = math.hypot(uav_state[assigned_uav]['base'][0] - uav_state[assigned_uav]['pos'][0],
                                         uav_state[assigned_uav]['base'][1] - uav_state[assigned_uav]['pos'][1])
                if uav_state[assigned_uav]['distance'] + dist_to_base > uav_state[assigned_uav]['max_range']:
                    constraint_violation += 1
                    execution_log.append({
                        'task_id': task_id, 'type': task_type, 'uav': assigned_uav,
                        'status': 'skipped', 'reason': 'insufficient flight range to reach the fire point'
                    })
                    continue
                dist_from_base = math.hypot(task['pos'][0] - uav_state[assigned_uav]['base'][0],
                                           task['pos'][1] - uav_state[assigned_uav]['base'][1])
                total_after = uav_state[assigned_uav]['distance'] + dist_to_base + dist_from_base
                if total_after > uav_state[assigned_uav]['max_range']:
                    constraint_violation += 1
                    execution_log.append({
                        'task_id': task_id, 'type': task_type, 'uav': assigned_uav,
                        'status': 'skipped', 'reason': 'insufficient flight range for the round trip'
                    })
                    continue
                candidates = [assigned_uav]

            best_uav = None
            best_start = float('inf')
            best_details = None

            for uav_id in candidates:
                uav = uav_state[uav_id]
                needs_refill = False
                dist_to_base = 0
                dist_from_base = 0

                if task_type == 2 and uav['ammo'] < task['hp']:
                    dist_to_base = math.hypot(uav['base'][0] - uav['pos'][0], uav['base'][1] - uav['pos'][1])
                    dist_from_base = math.hypot(task['pos'][0] - uav['base'][0], task['pos'][1] - uav['base'][1])
                    total_after = uav['distance'] + dist_to_base + dist_from_base
                    if total_after > uav['max_range']:
                        constraint_violation += 0.5
                        continue
                    needs_refill = True

                if needs_refill:
                    dist = dist_from_base
                else:
                    dist = math.hypot(task['pos'][0] - uav['pos'][0], task['pos'][1] - uav['pos'][1])

                if uav['distance'] + dist > uav['max_range']:
                    constraint_violation += 0.1
                    continue

                if needs_refill:
                    arrive_time = uav['time'] + dist_to_base / uav['speed'] + 5.0 + dist / uav['speed']
                else:
                    arrive_time = uav['time'] + dist / uav['speed']

                if task_type == 2:
                    window_start = task.get('window_start')
                    window_end = task.get('window_end')
                    if window_start is not None:
                        start_time = max(arrive_time, window_start)
                    else:
                        start_time = arrive_time
                    if window_end is not None and start_time > window_end:
                        total_delay_cost += (start_time - window_end) * 10
                else:
                    start_time = arrive_time

                if start_time < best_start:
                    best_start = start_time
                    best_uav = uav_id
                    best_details = {
                        'dist': dist,
                        'dist_to_base': dist_to_base,
                        'needs_refill': needs_refill
                    }

            if best_uav is None:
                execution_log.append({
                    'task_id': task_id, 'type': task_type, 'uav': assigned_uav,
                    'status': 'skipped', 'reason': 'no available UAV to execute'
                })
                continue

            uav = uav_state[best_uav]
            details = best_details

            if details['needs_refill']:
                uav['distance'] += details['dist_to_base']
                uav['time'] += details['dist_to_base'] / uav['speed'] + 5.0
                uav['pos'] = uav['base'][:2]
                uav['ammo'] = 3
                uav['distance'] += details['dist']
                uav['time'] = best_start
            else:
                uav['distance'] += details['dist']
                uav['time'] = best_start

            uav['pos'] = task['pos'][:2]
            if task_type == 2:
                uav['ammo'] -= task['hp']

            task_done[task_idx] = True
            fire_state[fire_id] = task_type
            makespan = max(makespan, uav['time'])

            execution_log.append({
                'task_id': task_id, 'type': task_type, 'uav': best_uav,
                'status': 'executed', 'start_time': best_start,
                'fire_id': fire_id, 'hp': task.get('hp', 0)
            })

            if task_type == 3:
                completed_fires.add(fire_id)
                total_reward += 3 * fire_value[fire_id] * fire_hp[fire_id]

        total_fly_cost = sum(uav_state[uid]['distance'] for uid in uav_state) * 3
        net_reward = total_reward - total_fly_cost - total_delay_cost
        penalty = constraint_violation * 1000
        fitness = net_reward - penalty
        return {
            'fitness': fitness,
            'net_reward': net_reward,
            'completed_fires': len(completed_fires),
            'makespan': makespan,
            'constraint_violation': constraint_violation,
            'execution_log': execution_log
        }

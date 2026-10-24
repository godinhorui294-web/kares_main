# ============================================================================
# Forest firefighting UAV scheduling - single-objective genetic algorithm
# (maximize net reward)
# Scale: 4 scout + 12 fighter UAVs, 5 rounds of ammunition each, 25 fire
# points, base at [25,25]
# ============================================================================

import json
import random
from copy import deepcopy
import math

# Simple numpy fallback for when numpy is unavailable
try:
    import numpy as np
    np_argsort = lambda x: np.argsort(x)
except ImportError:
    # Pure-Python argsort implementation
    def np_argsort(x):
        return sorted(range(len(x)), key=lambda i: x[i])

class SingleObjectiveScheduler:
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
            except NameError:
                pass  # numpy not available, skip


    def decode_chromosome(self, chromosome):
        n = self.num_tasks
        task_order = chromosome[:n]
        uav_assignment = chromosome[n:]
        return task_order, uav_assignment

    def simulate(self, chromosome):
        task_order, uav_assignment = self.decode_chromosome(chromosome)
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
        execution_log = []  # log of actually executed tasks

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
            'execution_log': execution_log  # execution log
        }


class SimpleGA:
    def __init__(self, scheduler, **kwargs):
        self.scheduler = scheduler
        self.pop_size = kwargs.get('pop_size', 600)
        self.generations = kwargs.get('generations', 150)
        self.crossover_rate = kwargs.get('crossover_rate', 0.8)
        self.mutation_rate = kwargs.get('mutation_rate', 0.2)
        self.tournament_size = kwargs.get('tournament_size', 3)
        self.elite_size = kwargs.get('elite_size', 0.05)
        self.patience = kwargs.get('patience', 100)
        self.num_tasks = scheduler.num_tasks
        self.task_ids = list(range(1, self.num_tasks + 1))
        self.scout_uavs = scheduler.scout_uavs
        self.fighter_uavs = scheduler.fighter_uavs

    def create_individual(self):
        task_order = []
        available = set(self.task_ids)
        prereq_done = {tid: True for tid in self.task_ids}
        prereq_map = {}
        for fire_id, tasks in self.scheduler.fire_tasks.items():
            if 1 in tasks and 2 in tasks:
                prereq_map[tasks[2] + 1] = tasks[1] + 1
            if 2 in tasks and 3 in tasks:
                prereq_map[tasks[3] + 1] = tasks[2] + 1
        while available:
            candidates = [tid for tid in available if prereq_done.get(tid, True)]
            if not candidates:
                candidates = list(available)
            fire_tasks = [tid for tid in candidates if self.scheduler.tasks[tid - 1]['type'] == 2]
            if fire_tasks and random.random() < 0.5:
                chosen = random.choice(fire_tasks)
            else:
                chosen = random.choice(candidates)
            task_order.append(chosen)
            available.remove(chosen)
            for tid, pre in prereq_map.items():
                if pre == chosen:
                    prereq_done[tid] = True
        uav_assignment = []
        for task_id in task_order:
            task = self.scheduler.tasks[task_id - 1]
            if task['type'] == 2:
                uav = random.choice(self.fighter_uavs)
            else:
                uav = random.choice(self.scout_uavs)
            uav_assignment.append(uav)
        return task_order + uav_assignment

    def evaluate(self, individual):
        result = self.scheduler.simulate(individual)
        return result['fitness'], result

    def select_parents(self, population, fitnesses):
        selected = []
        for _ in range(2):
            tournament = random.sample(range(len(population)), self.tournament_size)
            best = max(tournament, key=lambda i: fitnesses[i])
            selected.append(population[best])
        return selected

    def crossover(self, p1, p2):
        n = self.num_tasks
        if random.random() > self.crossover_rate:
            return p1[:]
        a, b = sorted(random.sample(range(n), 2))
        child_order = [None] * n
        child_order[a:b + 1] = p1[a:b + 1]
        p2_filtered = [x for x in p2[:n] if x not in child_order[a:b + 1]]
        idx = 0
        for i in list(range(a)) + list(range(b + 1, n)):
            child_order[i] = p2_filtered[idx]
            idx += 1
        p1_assign = p1[n:]
        p2_assign = p2[n:]
        child_assign = []
        for i in range(n):
            if random.random() < 0.5:
                child_assign.append(p1_assign[i])
            else:
                child_assign.append(p2_assign[i])
        return child_order + self._fix_assignment(child_order, child_assign)

    def _fix_assignment(self, task_order, uav_assignment):
        fixed = []
        for i, task_id in enumerate(task_order):
            task = self.scheduler.tasks[task_id - 1]
            assigned_uav = uav_assignment[i]
            required_type = self.scheduler.task_type_to_uav_type[task['type']]
            actual_type = None
            for u in self.scheduler.uavs:
                if u['id'] == assigned_uav:
                    actual_type = u['type']
                    break
            if required_type != actual_type:
                if task['type'] == 2:
                    assigned_uav = random.choice(self.fighter_uavs)
                else:
                    assigned_uav = random.choice(self.scout_uavs)
            fixed.append(assigned_uav)
        return fixed

    def mutate(self, ind):
        n = self.num_tasks
        new = ind[:]
        if random.random() < self.mutation_rate:
            op = random.choice(['swap', 'insert', 'inversion'])
            order = new[:n]
            if op == 'swap':
                i, j = random.sample(range(n), 2)
                order[i], order[j] = order[j], order[i]
            elif op == 'insert':
                idx = random.randint(0, n - 1)
                pos = random.randint(0, n - 1)
                gene = order.pop(idx)
                order.insert(pos, gene)
            elif op == 'inversion':
                a, b = sorted(random.sample(range(n), 2))
                order[a:b + 1] = reversed(order[a:b + 1])
            new[:n] = order
        if random.random() < self.mutation_rate:
            assign = new[n:]
            num_changes = random.randint(1, 3)
            for _ in range(num_changes):
                idx = random.randint(0, n - 1)
                task_id = new[idx]
                task = self.scheduler.tasks[task_id - 1]
                if task['type'] == 2:
                    assign[idx] = random.choice(self.fighter_uavs)
                else:
                    assign[idx] = random.choice(self.scout_uavs)
            new[n:] = assign
        return new

    def run(self, verbose=True):
        population = [self.create_individual() for _ in range(self.pop_size)]
        fitnesses = []
        results = []
        for ind in population:
            fit, res = self.evaluate(ind)
            fitnesses.append(fit)
            results.append(res)
        best_fitness = max(fitnesses)
        best_idx = fitnesses.index(best_fitness)
        best_result = results[best_idx]
        best_individual = deepcopy(population[best_idx])

        total_evaluations = self.pop_size
        generations_completed = 0

        if verbose:
            print(f"{'Gen':^6} | {'Fitness':^12} | {'NetReward':^12} | {'Fires':^6} | {'Makespan':^10} | {'CV':^8}")
            print("-" * 70)

        no_improve = 0
        for gen in range(self.generations):
            generations_completed = gen + 1
            new_pop = []
            elite_num = max(1, int(self.pop_size * self.elite_size))
            sorted_idx = np_argsort(fitnesses)[-elite_num:]
            for idx in sorted_idx:
                new_pop.append(deepcopy(population[idx]))
            while len(new_pop) < self.pop_size:
                p1, p2 = self.select_parents(population, fitnesses)
                child = self.crossover(p1, p2)
                child = self.mutate(child)
                new_pop.append(child)
            population = new_pop
            fitnesses = []
            results = []
            for ind in population:
                fit, res = self.evaluate(ind)
                fitnesses.append(fit)
                results.append(res)
            total_evaluations += self.pop_size
            current_best = max(fitnesses)
            status = ""
            if current_best > best_fitness + 1e-6:
                best_fitness = current_best
                best_idx = fitnesses.index(current_best)
                best_result = results[best_idx]
                best_individual = deepcopy(population[best_idx])
                no_improve = 0
                status = " *"
            else:
                no_improve += 1
                status = ""

            if verbose and (gen + 1) % 30 == 0:
                avg_fit = sum(fitnesses) / len(fitnesses)
                r = results[fitnesses.index(current_best)]
                print(f"{gen + 1:^6} | {current_best:^12.2f} | {r['net_reward']:^12.2f} | "
                      f"{r['completed_fires']:^6} | {r['makespan']:^10.2f} | {r['constraint_violation']:^8.2f}{status}")

            if no_improve >= self.patience:
                if verbose:
                    print(f"\nEarly stop: no improvement for {no_improve} generations")
                break

        if verbose:
            print(f"\nFinal result:")
            print(f"  Best fitness: {best_fitness:.2f}")
            print(f"  Net reward: {best_result['net_reward']:.2f}")
            print(f"  Completed fire points: {best_result['completed_fires']}")
            print(f"  Makespan: {best_result['makespan']:.2f}")
            print(f"  Constraint violations: {best_result['constraint_violation']:.2f}")
            print(f"  Total evaluations: {total_evaluations}")
            print(f"  Generations completed: {generations_completed}")

        return {
            'best_fitness': best_fitness,
            'best_result': best_result,
            'best_individual': best_individual,
            'evaluation_count': total_evaluations,
            'generations_completed': generations_completed
        }


if __name__ == "__main__":
    print("=" * 70)
    print("Forest Firefighting UAV Scheduling - Single-Objective GA (maximize net reward)")
    print("=" * 70)

    data_file = 'instances/firefighting_instance_010.json'
    scheduler = SingleObjectiveScheduler(data_file=data_file, random_seed=42)
    print(f"\nProblem scale:")
    print(f"  UAVs: {scheduler.num_uavs} (scout: {len(scheduler.scout_uavs)}, fighter: {len(scheduler.fighter_uavs)})")
    print(f"  Tasks: {scheduler.num_tasks} (fire points: {scheduler.num_fire_points})")
    print(f"  Chromosome length: {scheduler.num_tasks * 2}")

    print("\n" + "=" * 70)
    print("Running single-objective GA")
    print("=" * 70)

    ga = SimpleGA(scheduler, pop_size=600, generations=150, patience=80)
    result = ga.run(verbose=True)
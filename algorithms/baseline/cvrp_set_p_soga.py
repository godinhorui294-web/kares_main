# ============================================================================
# CVRPLib Set P - Capacitated Vehicle Routing Problem (CVRP) single-objective
# genetic algorithm
# Objective: minimize total travel distance (CVRP is a minimization problem)
# Proxy fitness convention: best_fitness = self.fitness_large - total_distance
#   Rationale: the pipeline compares by "maximization" end to end, so a proxy
#   maps the minimization objective onto maximization semantics.
#   fitness_large adapts to the instance scale (see
#   problems/cvrp_set_p/interface_contract.md) and is guaranteed to exceed the
#   total distance of any feasible solution, keeping fitness positive; the
#   constant cancels out in relative improvements, keeping label/vi signals
#   meaningful.
# Chromosome: customer permutation (1-indexed, depot excluded)
# Decoding: greedy split (accumulate demands along the permutation, open a new
# route on capacity overflow)
# Operators: OX crossover + swap/inversion/insert mutation + tournament
# selection + elitism
# Note: no 2-opt local search; left for the LLM to introduce autonomously
# ============================================================================

import json
import random

# Floor for the adaptive proxy constant; at load time an upper bound is
# estimated as 2*dim*max_edge and the larger value is used
FITNESS_LARGE_FLOOR = 3000


class CVRPScheduler:
    """CVRP scheduler: loads the instance, decodes a chromosome (customer permutation) into feasible routes, and computes the total distance."""

    def __init__(self, data_file, random_seed=None):
        with open(data_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        self.instance_id = data.get("instance_id", data.get("name", ""))
        self.dimension = data["dimension"]
        self.num_customers = data["num_customers"]
        self.capacity = data["capacity"]
        self.depot_id = data["depot_id"]
        self.distance_matrix = data["distance_matrix"]  # 2D list, index = id-1
        self.nodes = data["nodes"]
        # Customer id list (depot excluded)
        self.customer_ids = [n["id"] for n in self.nodes if not n.get("is_depot", False)]
        self.demands = {n["id"]: n["demand"] for n in self.nodes}
        # Adaptive LARGE: guaranteed > the total distance of any feasible solution
        # The worst feasible solution has at most 2*(dim-1) edges, each ≤ max_edge,
        # so 2*dim*max_edge is a safe upper bound
        max_edge = max(max(r) for r in self.distance_matrix) if self.distance_matrix else 0
        self.fitness_large = max(FITNESS_LARGE_FLOOR, 2 * self.dimension * max_edge)
        if random_seed is not None:
            random.seed(random_seed)

    def simulate(self, chromosome):
        """chromosome: permutation of customer ids. Returns a dict (with fitness / total_distance / routes)."""
        if not chromosome or len(chromosome) != self.num_customers:
            return {"fitness": 0, "total_distance": float("inf"), "routes": [], "feasible": False}

        routes = self._split_routes(chromosome)
        # Capacity check (greedy split satisfies it by construction; violated only
        # when a single customer's demand exceeds the capacity)
        for r in routes:
            if sum(self.demands[c] for c in r) > self.capacity:
                return {"fitness": 0, "total_distance": float("inf"), "routes": routes, "feasible": False}

        total_distance = 0
        for r in routes:
            if not r:
                continue
            prev = self.depot_id
            for c in r:
                total_distance += self.distance_matrix[prev - 1][c - 1]
                prev = c
            total_distance += self.distance_matrix[prev - 1][self.depot_id - 1]

        fitness = self.fitness_large - total_distance
        return {
            "fitness": fitness,
            "total_distance": total_distance,
            "routes": routes,
            "num_vehicles": len(routes),
            "feasible": True,
        }

    def _split_routes(self, chromosome):
        """Greedy split: accumulate demands along the permutation; open a new route on capacity overflow."""
        routes = []
        current = []
        current_load = 0
        for c in chromosome:
            d = self.demands[c]
            if current and current_load + d > self.capacity:
                routes.append(current)
                current = [c]
                current_load = d
            else:
                current.append(c)
                current_load += d
        if current:
            routes.append(current)
        return routes


class CVRPGA:
    """Single-objective genetic algorithm (maximizes the proxy fitness)."""

    def __init__(self, scheduler, **kwargs):
        self.scheduler = scheduler
        self.pop_size = kwargs.get("pop_size", 100)
        self.generations = kwargs.get("generations", 80)
        self.crossover_rate = kwargs.get("crossover_rate", 0.9)
        self.mutation_rate = kwargs.get("mutation_rate", 0.2)
        self.tournament_size = kwargs.get("tournament_size", 3)
        self.elite_size = max(1, kwargs.get("elite_size", 2))
        self.patience = kwargs.get("patience", 40)
        self.customer_ids = scheduler.customer_ids[:]
        self.num_customers = scheduler.num_customers

    def create_individual(self):
        ind = self.customer_ids[:]
        random.shuffle(ind)
        return ind

    def evaluate(self, ind):
        res = self.scheduler.simulate(ind)
        return res["fitness"], res

    def select_parents(self, pop, fits):
        selected = []
        for _ in range(2):
            tournament = random.sample(range(len(pop)), self.tournament_size)
            best = max(tournament, key=lambda i: fits[i])
            selected.append(pop[best])
        return selected

    def crossover(self, p1, p2):
        # Order Crossover (OX)
        if random.random() > self.crossover_rate:
            return p1[:]
        n = len(p1)
        a, b = sorted(random.sample(range(n), 2))
        child = [None] * n
        child[a:b + 1] = p1[a:b + 1]
        seg = set(p1[a:b + 1])
        rest = [x for x in p2 if x not in seg]
        idx = 0
        for i in list(range(0, a)) + list(range(b + 1, n)):
            child[i] = rest[idx]
            idx += 1
        return child

    def mutate(self, ind):
        if random.random() > self.mutation_rate:
            return ind[:]
        op = random.choice(["swap", "inversion", "insert"])
        new = ind[:]
        n = len(new)
        if op == "swap":
            i, j = random.sample(range(n), 2)
            new[i], new[j] = new[j], new[i]
        elif op == "inversion":
            a, b = sorted(random.sample(range(n), 2))
            new[a:b + 1] = reversed(new[a:b + 1])
        else:  # insert
            idx = random.randint(0, n - 1)
            pos = random.randint(0, n - 1)
            gene = new.pop(idx)
            new.insert(pos, gene)
        return new

    def run(self, verbose=False):
        pop = [self.create_individual() for _ in range(self.pop_size)]
        fits, results = [], []
        for ind in pop:
            f, r = self.evaluate(ind)
            fits.append(f)
            results.append(r)
        best_fitness = max(fits)
        best_idx = fits.index(best_fitness)
        best_result = results[best_idx]
        best_individual = list(pop[best_idx])
        eval_count = self.pop_size
        gens_completed = 0
        no_improve = 0

        for gen in range(self.generations):
            gens_completed = gen + 1
            order = sorted(range(len(pop)), key=lambda i: fits[i], reverse=True)
            new_pop = [list(pop[i]) for i in order[: self.elite_size]]
            while len(new_pop) < self.pop_size:
                p1, p2 = self.select_parents(pop, fits)
                child = self.crossover(p1, p2)
                child = self.mutate(child)
                new_pop.append(child)
            pop = new_pop
            fits, results = [], []
            for ind in pop:
                f, r = self.evaluate(ind)
                fits.append(f)
                results.append(r)
            eval_count += self.pop_size
            cur_best = max(fits)
            if cur_best > best_fitness + 1e-6:
                best_fitness = cur_best
                best_idx = fits.index(cur_best)
                best_result = results[best_idx]
                best_individual = list(pop[best_idx])
                no_improve = 0
            else:
                no_improve += 1
            if no_improve >= self.patience:
                break

        return {
            "best_fitness": best_fitness,
            "best_result": best_result,
            "best_individual": best_individual,
            "evaluation_count": eval_count,
            "generations_completed": gens_completed,
        }


if __name__ == "__main__":
    import sys
    data_file = sys.argv[1] if len(sys.argv) > 1 else "instances/cvrp_set_p/P-n16-k8.json"
    sched = CVRPScheduler(data_file=data_file, random_seed=42)
    print(f"Instance: {sched.instance_id} | customers: {sched.num_customers} | capacity: {sched.capacity}")
    ga = CVRPGA(sched, pop_size=100, generations=80)
    res = ga.run(verbose=False)
    br = res["best_result"]
    print(f"best_fitness={res['best_fitness']} (distance={br['total_distance']}, "
          f"vehicles={br['num_vehicles']}, evals={res['evaluation_count']})")

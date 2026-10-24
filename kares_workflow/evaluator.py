"""
kares_workflow.evaluator — run candidate algorithms on test instances and
collect fitness.

Design notes:
- subprocess isolation: every instance runs in its own subprocess so dead
  loops / crashes never take down the main process.
- timeout control: EVAL_TIME_BUDGET_PER_INST seconds per instance.
- automatic algorithm-class location: AST-based detection of the
  [scheduler class] (__init__ taking data_file) and the [algorithm class]
  (__init__ taking scheduler, or a class name matching
  GA/Algorithm/Optimizer/PSO/SA/DE/Search). Module-level constants
  SCHEDULER_CLASS / SOLVER_CLASS can pin them explicitly.
- see config.INTERFACE_CONTRACT for the interface contract.
"""
import ast
import json
import os
import statistics
import subprocess
import sys
import textwrap
from typing import List, Dict, Optional

from . import config

_ALGO_NAME_HINTS = ("GA", "Algorithm", "Optimizer", "PSO", "SA", "DE",
                    "Search", "Evolution", "ABC", "Tabu", "Harmony")


def _list_classes(code: str) -> List[Dict]:
    """AST-parse top-level classes; returns [{name, init_args: [...]}]."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            init_args = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                    init_args = [a.arg for a in item.args.args]
                    break
            classes.append({"name": node.name, "init_args": init_args})
    return classes


def find_scheduler_and_algorithm_classes(code: str) -> Optional[Dict]:
    """
    Locate the scheduler class and the algorithm class.
    Scheduler class: __init__ takes 'data_file'.
    Algorithm class: __init__ takes 'scheduler', or the class name contains
    an _ALGO_NAME_HINTS entry and it is not the scheduler class.
    """
    classes = _list_classes(code)
    if not classes:
        return None

    scheduler_cls = None
    for c in classes:
        if "data_file" in c["init_args"]:
            scheduler_cls = c["name"]
            break
    # fallback: class name containing Scheduler
    if not scheduler_cls:
        for c in classes:
            if "Scheduler" in c["name"]:
                scheduler_cls = c["name"]
                break

    algo_cls = None
    # 1) prefer a class whose __init__ takes 'scheduler'
    for c in classes:
        if c["name"] == scheduler_cls:
            continue
        if "scheduler" in c["init_args"]:
            algo_cls = c["name"]
            break
    # 2) fallback: class name matches a hint
    if not algo_cls:
        for c in classes:
            if c["name"] == scheduler_cls:
                continue
            if any(h in c["name"] for h in _ALGO_NAME_HINTS):
                algo_cls = c["name"]
                break
    # 3) last resort: the first non-scheduler class
    if not algo_cls:
        for c in classes:
            if c["name"] != scheduler_cls:
                algo_cls = c["name"]
                break

    if not scheduler_cls and not algo_cls:
        return None
    return {"scheduler": scheduler_cls, "algorithm": algo_cls, "classes": classes}


# Evaluation script run inside the subprocess (standalone; shares no memory with the parent)
# __POP_SIZE__ / __GENERATIONS__ / __BUDGET__ are replaced with config values
# when the runner file is written (see _run_one).
_RUNNER_TEMPLATE = textwrap.dedent('''
import ast, json, os, sys, importlib.util, traceback

candidate_path = sys.argv[1]
instance_path = sys.argv[2]
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
env_scheduler_path = sys.argv[4] if len(sys.argv) > 4 else ""

# ---- workflow-pinned compute scale (config.kares_workflow values) ----
# EVAL_BUDGET is the hard evaluation ceiling: the guaranteed 90000-evaluation
# budget plus a grace margin (see config.EVAL_BUDGET_MARGIN).
POP_SIZE = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else __POP_SIZE__
GENERATIONS = int(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[6] else __GENERATIONS__
EVAL_BUDGET = int(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7] else __BUDGET__

_ALGO_HINTS = ("GA","Algorithm","Optimizer","PSO","SA","DE","Search","Evolution","ABC","Tabu","Harmony")


class _BudgetExhausted(BaseException):
    """Raised by the budgeted scheduler when the evaluation budget is spent.

    Derives from BaseException (not Exception) so candidate code that wraps
    evaluate() calls in a broad `except Exception` cannot swallow it and
    keep looping on dead evaluations.
    """
    pass


class _BudgetedScheduler(object):
    """Proxy around the environment scheduler that hard-caps fitness evaluations.

    Counts simulate()/simulate_decoded() calls; the call that would exceed
    EVAL_BUDGET raises _BudgetExhausted instead of evaluating. Every other
    attribute access is delegated to the wrapped scheduler. It also tracks
    the best fitness seen across all evaluations at the scheduler level, so
    the best-so-far can be recovered even if the candidate does not record it.
    """

    def __init__(self, inner, budget):
        self._inner = inner
        self._budget = int(budget)
        self.evals_used = 0
        self.best_seen_fitness = None
        self.best_seen_input = None

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _spend(self):
        if self.evals_used >= self._budget:
            raise _BudgetExhausted()
        self.evals_used += 1

    def _track(self, eval_input, result):
        if isinstance(result, dict):
            f = result.get("fitness")
            if isinstance(f, (int, float)) and (
                    self.best_seen_fitness is None or f > self.best_seen_fitness):
                self.best_seen_fitness = float(f)
                self.best_seen_input = eval_input

    def simulate(self, *args, **kwargs):
        self._spend()
        result = self._inner.simulate(*args, **kwargs)
        self._track(args[0] if args else kwargs.get("chromosome"), result)
        return result

    def simulate_decoded(self, *args, **kwargs):
        self._spend()
        result = self._inner.simulate_decoded(*args, **kwargs)
        self._track({"task_order": args[0] if args else None,
                     "uav_assignment": args[1] if len(args) > 1 else None}, result)
        return result


def _extract_best(obj):
    """Recover the best-so-far fitness from a partially-run algorithm object."""
    for name in ("best_fitness", "best_score", "gbest_fitness",
                 "global_best_fitness", "best_fit", "best_val"):
        v = getattr(obj, name, None)
        if isinstance(v, (int, float)):
            return float(v)
    vals = [float(v) for k, v in vars(obj).items()
            if isinstance(v, (int, float)) and "best" in k.lower()]
    return max(vals) if vals else None


def _extract_best_result(obj):
    for name in ("best_result", "best_solution", "best_individual"):
        v = getattr(obj, name, None)
        if isinstance(v, (dict, list)):
            return v
    return None


def list_classes(code):
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [], str(e)
    classes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            init_args = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                    init_args = [a.arg for a in item.args.args]
                    break
            classes.append({"name": node.name, "init_args": init_args})
    return classes, None

def find(classes):
    """Identify the scheduler class (to skip) and the algorithm class (to instantiate)."""
    scheduler_cls = None
    for c in classes:
        if "data_file" in c["init_args"]:
            scheduler_cls = c["name"]; break
    if not scheduler_cls:
        for c in classes:
            if "Scheduler" in c["name"]:
                scheduler_cls = c["name"]; break
    algo_cls = None
    for c in classes:
        if c["name"] == scheduler_cls: continue
        if "scheduler" in c["init_args"]:
            algo_cls = c["name"]; break
    if not algo_cls:
        for c in classes:
            if c["name"] == scheduler_cls: continue
            if any(h in c["name"] for h in _ALGO_HINTS):
                algo_cls = c["name"]; break
    if not algo_cls:
        for c in classes:
            if c["name"] != scheduler_cls:
                algo_cls = c["name"]; break
    return scheduler_cls, algo_cls

def main():
    with open(candidate_path, "r", encoding="utf-8") as f:
        code = f.read()
    classes, syn_err = list_classes(code)
    if syn_err:
        print("===RESULT_JSON===")
        print(json.dumps({"ok": False, "error": "syntax: " + syn_err, "best_fitness": None}))
        return
    sched_name, algo_name = find(classes)
    # explicit constant override
    spec = importlib.util.spec_from_file_location("__candidate__", candidate_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        print("===RESULT_JSON===")
        print(json.dumps({"ok": False, "error": "import: " + repr(e), "best_fitness": None}))
        return
    algo_name = getattr(mod, "SOLVER_CLASS", algo_name) or getattr(mod, "ALGORITHM_CLASS", algo_name)

    if not algo_name:
        print("===RESULT_JSON===")
        print(json.dumps({"ok": False, "error": "no algorithm class found", "best_fitness": None}))
        return
    try:
        # ── scheduler instantiation ──
        # Prefer the fixed environment scheduler (env_scheduler_path) so
        # candidates cannot tamper with the fitness formula.
        raw_scheduler = None
        if env_scheduler_path and os.path.exists(env_scheduler_path):
            env_spec = importlib.util.spec_from_file_location("__env_scheduler__", env_scheduler_path)
            env_mod = importlib.util.module_from_spec(env_spec)
            env_spec.loader.exec_module(env_mod)
            env_cls = getattr(env_mod, "EnvScheduler", None)
            if env_cls is None:
                # fallback: any class in the env module exposing simulate()
                for name in dir(env_mod):
                    obj = getattr(env_mod, name)
                    if isinstance(obj, type) and hasattr(obj, "simulate"):
                        env_cls = obj; break
            if env_cls is None:
                raise RuntimeError("EnvScheduler class not found in the env_scheduler module")
            raw_scheduler = env_cls(data_file=instance_path, random_seed=seed)
        elif sched_name and hasattr(mod, sched_name):
            # fallback: the candidate's own scheduler (backward compatibility)
            raw_scheduler = getattr(mod, sched_name)(data_file=instance_path, random_seed=seed)

        # hard evaluation budget around whichever scheduler is used
        scheduler = _BudgetedScheduler(raw_scheduler, EVAL_BUDGET) if raw_scheduler is not None else instance_path

        algo_cls = getattr(mod, algo_name)
        import inspect
        sig = inspect.signature(algo_cls.__init__)
        params = sig.parameters
        # pinned compute scale: pass pop_size/generations when the constructor
        # can accept them (named params or **kwargs), overriding file defaults
        pinned = {}
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            pinned = {"pop_size": POP_SIZE, "generations": GENERATIONS}
        else:
            for k, v in (("pop_size", POP_SIZE), ("generations", GENERATIONS)):
                if k in params:
                    pinned[k] = v
        if "data_file" in params and "scheduler" not in params:
            algo = algo_cls(data_file=instance_path, random_seed=seed, **pinned)
        else:
            algo = algo_cls(scheduler, **pinned)
        budget_exhausted = False
        try:
            result = algo.run(verbose=False)
        except _BudgetExhausted:
            budget_exhausted = True
            result = None
        evals_used = getattr(scheduler, "evals_used", None) if raw_scheduler is not None else None
        if budget_exhausted:
            # prefer scheduler-level best tracking (algorithm-agnostic),
            # fall back to attributes on the partially-run algorithm object
            bf = getattr(scheduler, "best_seen_fitness", None) if raw_scheduler is not None else None
            best_input = getattr(scheduler, "best_seen_input", None) if raw_scheduler is not None else None
            if bf is None:
                bf = _extract_best(algo)
            if bf is None:
                print("===RESULT_JSON===")
                print(json.dumps({"ok": False,
                                  "error": "eval budget exhausted before any fitness was recorded",
                                  "best_fitness": None, "evals_used": evals_used,
                                  "budget_exhausted": True}))
                return
            print("===RESULT_JSON===")
            print(json.dumps({"ok": True, "best_fitness": bf,
                              "best_result": _extract_best_result(algo),
                              "best_eval_input": best_input,
                              "generations_completed": None,
                              "evals_used": evals_used, "budget_exhausted": True}))
            return
        bf = result.get("best_fitness") if isinstance(result, dict) else None
        print("===RESULT_JSON===")
        print(json.dumps({"ok": True, "best_fitness": bf,
                           "best_result": result.get("best_result") if isinstance(result, dict) else None,
                           "generations_completed": result.get("generations_completed") if isinstance(result, dict) else None,
                           "evals_used": evals_used, "budget_exhausted": False}))
    except _BudgetExhausted:
        print("===RESULT_JSON===")
        print(json.dumps({"ok": False,
                          "error": "eval budget exhausted during algorithm setup",
                          "best_fitness": None, "budget_exhausted": True}))
    except Exception as e:
        print("===RESULT_JSON===")
        print(json.dumps({"ok": False, "error": "runtime: " + repr(e), "traceback": traceback.format_exc()[-1500:], "best_fitness": None}))

main()
''').strip()


def _run_one(candidate_path: str, instance_path: str, seed: int,
             timeout: int = config.EVAL_TIME_BUDGET_PER_INST,
             env_scheduler_path: str = "",
             pop_size: Optional[int] = None,
             generations: Optional[int] = None,
             budget: Optional[int] = None) -> Dict:
    """Run a single instance in a subprocess; returns the result dict.

    pop_size/generations/budget default to the pinned workflow values in
    config (EVAL_POP_SIZE / EVAL_GENERATIONS / EVAL_BUDGET); passing explicit
    values overrides them (used for smoke tests). The effective hard ceiling
    for a default run is EVAL_BUDGET + EVAL_BUDGET_MARGIN: the guaranteed
    budget of 90000 evaluations plus a grace margin so multi-island /
    multi-population structures can complete their natural loop without
    being truncated mid-generation. Explicit test budgets are exact (no
    margin).
    """
    runner_path = os.path.join(config.OUTPUTS_DIR, "_eval_runner.py")
    os.makedirs(os.path.dirname(runner_path), exist_ok=True)
    if budget is not None:
        eval_ceiling = budget
    else:
        eval_ceiling = config.EVAL_BUDGET + config.EVAL_BUDGET_MARGIN
    runner_code = (_RUNNER_TEMPLATE
                   .replace("__POP_SIZE__", str(pop_size or config.EVAL_POP_SIZE))
                   .replace("__GENERATIONS__", str(generations or config.EVAL_GENERATIONS))
                   .replace("__BUDGET__", str(eval_ceiling)))
    with open(runner_path, "w", encoding="utf-8") as f:
        f.write(runner_code)

    try:
        proc = subprocess.run(
            [sys.executable, runner_path, candidate_path, instance_path, str(seed),
             env_scheduler_path or "",
             str(pop_size) if pop_size else "",
             str(generations) if generations else "",
             str(budget) if budget else ""],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timeout({timeout}s)", "best_fitness": None}
    except Exception as e:
        return {"ok": False, "error": f"subprocess: {repr(e)}", "best_fitness": None}

    out = proc.stdout or ""
    marker = "===RESULT_JSON==="
    if marker in out:
        json_part = out.split(marker, 1)[1].strip()
        # take the last JSON line (guard against stray prints)
        try:
            return json.loads(json_part.splitlines()[-1])
        except Exception:
            # try the whole block
            try:
                return json.loads(json_part)
            except Exception:
                pass
    err = (proc.stderr or "")[-800:]
    return {"ok": False, "error": "no result marker. stderr: " + err, "best_fitness": None}


def evaluate_algorithm(candidate_path: str, instance_files: List[str],
                       seed: int = 42,
                       timeout_per_inst: int = config.EVAL_TIME_BUDGET_PER_INST,
                       env_scheduler_path: str = "") -> Dict:
    """
    Evaluate a candidate algorithm across multiple instances.

    Returns:
        {
            fitnesses: List[float],      # per-instance best_fitness (None on failure)
            mean_fitness: float,         # mean over successful instances (-inf when none)
            std: float,
            completed: int,              # number of successful instances
            total: int,
            errors: List[str],
            ok: bool,                    # at least one instance succeeded
            evals_used: List[Optional[int]],   # per-instance scheduler evaluations
            budget_exhausted_count: int, # instances that hit the eval budget
        }
    """
    fitnesses: List[Optional[float]] = []
    errors = []
    evals_used: List[Optional[int]] = []
    budget_exhausted_count = 0
    for inst in instance_files:
        res = _run_one(candidate_path, inst, seed, timeout=timeout_per_inst,
                       env_scheduler_path=env_scheduler_path)
        evals_used.append(res.get("evals_used"))
        if res.get("budget_exhausted"):
            budget_exhausted_count += 1
        if res.get("ok") and res.get("best_fitness") is not None:
            fitnesses.append(float(res["best_fitness"]))
        else:
            fitnesses.append(None)
            errors.append(f"{os.path.basename(inst)}: {res.get('error', 'unknown')[:200]}")

    valid = [f for f in fitnesses if f is not None]
    mean_f = statistics.mean(valid) if valid else float("-inf")
    std_f = statistics.pstdev(valid) if len(valid) > 1 else 0.0
    return {
        "fitnesses": fitnesses,
        "mean_fitness": mean_f,
        "std": std_f,
        "completed": len(valid),
        "total": len(instance_files),
        "errors": errors,
        "ok": len(valid) > 0,
        "evals_used": evals_used,
        "budget_exhausted_count": budget_exhausted_count,
    }


def evaluate_baseline(baseline_path: str, instance_files: List[str],
                      seed: int = 42, env_scheduler_path: str = "") -> Dict:
    """Evaluate the baseline algorithm (same interface as candidates)."""
    return evaluate_algorithm(baseline_path, instance_files, seed=seed,
                              env_scheduler_path=env_scheduler_path)

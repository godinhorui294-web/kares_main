"""
kares_workflow.mechanical_barrier — mechanical barrier: an evaluate →
improve → verify loop.

Pipeline (at most BARRIER_MAX_ROUNDS rounds):
  1. Mechanical pre-checks (no LLM): AST syntax + interface contract
     (locating the scheduler / algorithm classes).
  2. Sandbox pre-run: subprocess trial on the first instance, capturing
     runtime errors.
  3. If the pre-check / pre-run fails → evaluation agent (LLM) reports →
     improvement agent (LLM) repairs → verification agent (LLM) confirms →
     the repaired code moves on to the next round.
  4. PASS returns viable code; FAIL returns the failure plus a forbidden
     constraint (for sedimentation).

Designed to minimize LLM calls: mechanical pre-checks and the sandbox run
first; the LLM is only invoked on failure.
"""
import ast
import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

from . import config
from .llm_client import LLMClient
from .problem_loader import ProblemLoader
from .evaluator import find_scheduler_and_algorithm_classes, _run_one, evaluate_algorithm
from .coders import extract_code, apply_diff_with_retry
from .coders.diff_prompts import build_diff_format_suffix


def _syntax_check(code: str) -> Optional[str]:
    """Return the syntax error message, or None when the code parses."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError (line {e.lineno}): {e.msg}"


def _interface_check(code: str) -> Tuple[bool, str, Optional[Dict]]:
    """Check the interface contract: whether an algorithm class can be located
    (the scheduler is environment-provided; candidates need not bundle one).
    Returns (ok, msg, classes_info)."""
    info = find_scheduler_and_algorithm_classes(code)
    if info is None or not info.get("algorithm"):
        return False, "failed to locate an algorithm class (__init__ taking scheduler, or a name matching the algorithm hints)", info
    sched_note = f", scheduler class={info['scheduler']}" if info.get("scheduler") else " (scheduler provided by the environment)"
    return True, f"algorithm class={info['algorithm']}{sched_note}", info


class MechanicalBarrier:
    """Mechanical barrier."""

    def __init__(self, llm: LLMClient, problem: ProblemLoader,
                 max_rounds: int = config.BARRIER_MAX_ROUNDS):
        self.llm = llm
        self.problem = problem
        self.max_rounds = max_rounds

    def barrier(self, candidate: Dict, instance_file: Optional[str] = None,
                instance_files: Optional[List[str]] = None,
                baseline_fitness: Optional[float] = None,
                seed: int = 42) -> Dict:
        """
        Run the barrier pipeline on a candidate.

        Args:
            candidate: {path, code, ...}
            instance_file: single instance for the sandbox pre-run (legacy
              interface; instance_files preferred)
            instance_files: instances for quick evaluation (pass all of them;
              the barrier takes its own subset)
            baseline_fitness: baseline fitness used for performance verification
        Returns:
            {passed, code, path, rounds, report, forbidden_pattern, quick_eval}
        """
        code = candidate["code"]
        path = candidate["path"]

        eval_report = None
        for rnd in range(1, self.max_rounds + 1):
            # 1. mechanical pre-checks + quick evaluation (performance verification)
            report = self._build_eval_report(
                code, path, instance_file, instance_files,
                baseline_fitness, seed,
            )
            eval_report = report
            if report["verdict"] == "PASS":
                quick = report.get("quick_eval")
                sandbox_f = quick.get("mean_fitness") if quick else None
                return {"passed": True, "code": code, "path": path,
                        "rounds": rnd, "report": report,
                        "sandbox_fitness": sandbox_f,
                        "quick_eval": quick}

            # 2. improvement agent:
            #    repair strategy is controlled by config.BARRIER_USE_DIFF:
            #    - True: SEARCH/REPLACE patches (diff mode)
            #    - False: full rewrite (base mode, the current default; the
            #      diff format is not stable enough)
            use_diff = config.BARRIER_USE_DIFF
            repaired = self._improve(code, report, use_diff=use_diff)
            if not repaired:
                # repair failed; try the next round
                continue

            # 3. verification agent (LLM structural-consistency check)
            verified = self._verify(code, repaired, report)
            code = repaired
            _write(path, code)  # persist the update
            if verified.get("verdict") != "PASS":
                # merge the new issues found by the verification agent for the next repair round
                report["errors"].extend([
                    {"err_type": "verification", "loc": "verify_agent",
                     "description": e,
                     "fix_suggestion": "new issue found by the verification agent"}
                    for e in verified.get("new_errors", [])
                ])
            # the next round reruns the full pre-check + quick evaluation

        # all rounds failed
        forbidden = self._make_forbidden_pattern(candidate, eval_report)
        return {"passed": False, "code": code, "path": path,
                "rounds": self.max_rounds, "report": eval_report,
                "forbidden_pattern": forbidden, "quick_eval": None}

    def _build_eval_report(self, code: str, path: str,
                           instance_file: Optional[str],
                           instance_files: Optional[List[str]],
                           baseline_fitness: Optional[float],
                           seed: int) -> Dict:
        """Build an evaluation report covering syntax, interface, runtime and performance dimensions."""
        # syntax
        syn_err = _syntax_check(code)
        if syn_err:
            return {"verdict": "FAIL", "errors": [
                {"err_type": "syntax", "loc": "?", "description": syn_err,
                 "fix_suggestion": "fix the syntax error"}],
                "summary": syn_err, "quick_eval": None,
                "baseline_fitness": baseline_fitness}

        # interface
        ok, msg, info = _interface_check(code)
        if not ok:
            return {"verdict": "FAIL", "errors": [
                {"err_type": "constraint", "loc": "class",
                 "description": msg,
                 "fix_suggestion": "make sure the code exposes a scheduler class with __init__(self, data_file) and an algorithm class with __init__(self, scheduler)"}],
                "summary": msg, "quick_eval": None,
                "baseline_fitness": baseline_fitness}

        run_path = _resolve_run_path(code, path)
        quick = None
        quick_count = config.BARRIER_QUICK_EVAL_INSTANCES

        if instance_files and quick_count > 0:
            # quick evaluation: full evaluate_algorithm on a subset of the real instances
            quick_files = instance_files[:quick_count]
            quick = evaluate_algorithm(
                run_path, quick_files, seed=seed,
                timeout_per_inst=config.EVAL_TIME_BUDGET_PER_INST,
                env_scheduler_path=self.problem.env_scheduler_path,
            )
        else:
            # legacy behavior: single-instance sandbox pre-run
            inst = instance_file or (self.problem.get_instances(1) or [None])[0]
            if inst:
                sandbox = _run_one(run_path, inst, seed, timeout=120,
                                   env_scheduler_path=self.problem.env_scheduler_path)
                if not sandbox.get("ok"):
                    err = sandbox.get("error", "unknown")[:600]
                    return {"verdict": "FAIL", "errors": [
                        {"err_type": "runtime", "loc": "run()",
                         "description": err,
                         "fix_suggestion": "fix the runtime error so run() returns best_fitness normally"}],
                        "summary": "sandbox run failed", "quick_eval": None,
                        "baseline_fitness": baseline_fitness}
                quick = {
                    "ok": True,
                    "mean_fitness": sandbox.get("best_fitness"),
                    "completed": 1, "total": 1, "std": 0.0,
                    "errors": [],
                    "fitnesses": [sandbox.get("best_fitness")],
                }

        # performance / quality checks
        perf_errs = self._performance_errors(quick, baseline_fitness) if quick else []
        if perf_errs:
            return {"verdict": "FAIL", "errors": perf_errs,
                    "summary": "quick evaluation failed the performance/runtime checks",
                    "quick_eval": quick,
                    "baseline_fitness": baseline_fitness}

        return {"verdict": "PASS", "errors": [],
                "summary": "quick evaluation passed", "quick_eval": quick,
                "baseline_fitness": baseline_fitness}

    # EnvScheduler attributes/methods (referenced by _gen_fix_suggestion)
    _ENV_SCHEDULER_INTERFACE = (
        "EnvScheduler available attributes: num_tasks, num_uavs, num_fire_points, "
        "tasks, uavs, fire_points, fire_tasks, scout_uavs, fighter_uavs, "
        "task_type_to_uav_type, base_pos. "
        "Available methods: simulate(chromosome), simulate_decoded(task_order, uav_assignment), "
        "decode_chromosome(chromosome). "
        "simulate() takes a single chromosome argument (a list) and no extra keyword "
        "arguments such as cost_weight/delay_weight. "
        "simulate() returns a dict with keys including: fitness, net_reward, "
        "completed_fires, makespan, constraint_violation, total_distance, "
        "total_delay, fly_cost, delay_cost."
    )

    def _gen_fix_suggestion(self, err_msg: str) -> str:
        """Generate concrete repair guidance from a runtime error message."""
        msg = err_msg.lower()

        # AttributeError: missing EnvScheduler attribute
        m = re.search(r"attributeerror.*'envscheduler'.*has no attribute '(\w+)'", msg)
        if m:
            attr = m.group(1)
            return (
                f"EnvScheduler has no attribute '{attr}'. {self._ENV_SCHEDULER_INTERFACE} "
                f"Derive {attr} yourself inside the algorithm class __init__ from the "
                f"standard attributes, e.g. from scheduler.tasks / scheduler.fire_points / scheduler.uavs."
            )

        # TypeError: argument not accepted by simulate()
        m = re.search(r"typeerror.*simulate\(\).*unexpected keyword argument '(\w+)'", msg)
        if m:
            kw = m.group(1)
            return (
                f"EnvScheduler.simulate() does not accept the argument '{kw}'. {self._ENV_SCHEDULER_INTERFACE} "
                f"1) remove the {kw} argument from the simulate() call inside evaluate(); "
                f"2) move custom weighting/control logic into the algorithm class's evaluate(), "
                f"post-processing the result['fitness'] returned by simulate()."
            )

        # TypeError: wrong argument count for simulate()
        m = re.search(r"typeerror.*simulate\(\).*takes \d+.*but \d+ were given", msg)
        if m:
            return (
                f"EnvScheduler.simulate(chromosome) takes exactly one positional argument. {self._ENV_SCHEDULER_INTERFACE} "
                f"Remove the extra arguments, or move custom logic inside the algorithm class."
            )

        # TypeError: wrong arguments for simulate_decoded()
        m = re.search(r"typeerror.*simulate_decoded\(\).*", msg)
        if m:
            return (
                f"simulate_decoded(task_order, uav_assignment) takes two list arguments. "
                f"task_order: task IDs (1-based); uav_assignment: UAV IDs; both must have equal length."
            )

        # KeyError: missing key in the result dict
        m = re.search(r"keyerror.*['\"]?(\w+)['\"]?", msg)
        if m:
            key = m.group(1)
            return (
                f"Key '{key}' does not exist in the result dict. {self._ENV_SCHEDULER_INTERFACE} "
                f"Check the key name, or access it safely via result.get('{key}')."
            )

        # NameError: undefined variable
        m = re.search(r"nameerror.*name '(\w+)' is not defined", msg)
        if m:
            name = m.group(1)
            return (
                f"Variable '{name}' is not defined. Check for a missing import or a "
                f"misplaced initialization (e.g. referencing a self attribute outside __init__)."
            )

        # IndexError: out of range
        if "indexerror" in msg:
            return (
                "List index out of range. Check: 1) the chromosome length equals 2*num_tasks; "
                "2) task_order IDs stay within 1..num_tasks; "
                "3) uav_assignment IDs are valid UAV IDs."
            )

        # TimeoutError / timeouts
        if "timeout" in msg or "timed out" in msg:
            return (
                "Algorithm timed out. Check: 1) population size / iteration count is too large; "
                "2) dead loops or unbounded recursion inside evaluate(); "
                "3) a non-converging while loop in local_search."
            )

        # ZeroDivisionError
        if "zerodivisionerror" in msg:
            return (
                "Division by zero. Check: 1) the population size is 0; "
                "2) denominators of statistics (e.g. mean distance) can be 0 — add a guard."
            )

        # catch-all
        return (
            "Fix the runtime error. Follow the interface contract when using EnvScheduler. "
            f"{self._ENV_SCHEDULER_INTERFACE}"
        )

    def _performance_errors(self, quick: Dict,
                            baseline_fitness: Optional[float]) -> List[Dict]:
        """Build the performance error list from quick-evaluation results; empty when clean."""
        errors = []
        if not quick.get("ok"):
            for err in quick.get("errors", []):
                errors.append({
                    "err_type": "runtime",
                    "loc": "quick_eval",
                    "description": f"quick evaluation failed: {err[:300]}",
                    "fix_suggestion": self._gen_fix_suggestion(err),
                })
            return errors

        mean_f = quick.get("mean_fitness")
        if mean_f is None or (isinstance(mean_f, float) and math.isnan(mean_f)) or mean_f == float("-inf"):
            errors.append({
                "err_type": "performance",
                "loc": "mean_fitness",
                "description": f"quick evaluation produced invalid fitness: {mean_f}",
                "fix_suggestion": (
                    "run() did not return a valid best_fitness. Check: "
                    "1) run() calls evaluate() properly and records the best solution; "
                    "2) evaluate() calls scheduler.simulate() properly and extracts result['fitness']; "
                    "3) not every instance crashed, leaving no valid fitness."
                ),
            })
        else:
            completed = quick.get("completed", 0)
            total = quick.get("total", 0)
            if total > 0 and completed < total:
                # surface the errors of the failed portion
                partial_errs = [e for e in quick.get("errors", []) if e]
                if partial_errs:
                    fix = self._gen_fix_suggestion(partial_errs[0])
                else:
                    fix = "Check boundary-condition handling on the instances that failed (e.g. differing task/UAV counts)."
                errors.append({
                    "err_type": "performance",
                    "loc": "quick_eval",
                    "description": f"quick evaluation succeeded on only {completed}/{total} instances",
                    "fix_suggestion": fix,
                })
            if completed > 1 and quick.get("std", 0) == 0:
                errors.append({
                    "err_type": "performance",
                    "loc": "fitness_distribution",
                    "description": "all successful instances returned identical fitness; possible degenerate results or no real optimization",
                    "fix_suggestion": (
                        "Check: 1) the algorithm uses different random seeds per instance; "
                        "2) evaluate() actually calls scheduler.simulate() instead of hardcoding results; "
                        "3) run() is not caching a previous result."
                    ),
                })
            if (baseline_fitness is not None and baseline_fitness > 0
                    and config.BARRIER_PERFORMANCE_FLOOR_RATIO > 0):
                floor = baseline_fitness * config.BARRIER_PERFORMANCE_FLOOR_RATIO
                if mean_f < floor:
                    errors.append({
                        "err_type": "performance",
                        "loc": "fitness_quality",
                        "description": (f"quick-eval mean_fitness={mean_f:.2f} is far below "
                                        f"baseline={baseline_fitness:.2f} (floor {floor:.2f})"),
                        "fix_suggestion": (
                            f"Solution quality is far below the baseline ({mean_f:.0f} vs {baseline_fitness:.0f}). "
                            "Common causes: "
                            "1) heavy constraint violations accumulating penalty=1000×violation — "
                            "check that task_order respects the scout→firefight→recheck order and "
                            "that uav_assignment matches UAV types (scout=recon, fighter=firefighting); "
                            "2) unreasonable UAV assignments leaving tasks unexecutable — "
                            "check fuel range and ammunition capacity; "
                            "3) a poor initialization strategy — try greedy initialization instead of purely random."
                        ),
                    })
        return errors

    # ---- LLM sub-agents ----
    def _improve(self, code: str, report: Dict, use_diff: bool = False) -> Optional[str]:
        """Improvement agent: SEARCH/REPLACE patch repair when use_diff=True, otherwise full rewrite."""
        import logging
        logger = logging.getLogger("kares")

        if use_diff:
            logger.info("  repair strategy: SEARCH/REPLACE patch")
            return self._improve_diff(code, report)
        else:
            logger.info("  repair strategy: full rewrite")
            return self._improve_full(code, report)

    def _improve_full(self, code: str, report: Dict) -> Optional[str]:
        """Full-rewrite repair."""
        tmpl = self.problem.load_prompt_template("barrier", "improvement.md")
        prompt = self.problem.render_prompt(
            tmpl, candidate_code=code,
            eval_report=json.dumps(report, ensure_ascii=False, indent=2),
        )
        messages = [
            {"role": "system", "content": "You are a code repair expert. Output only the fully repaired code plus a brief repair note."},
            {"role": "user", "content": prompt},
        ]
        out = self.llm.chat(messages, role="barrier")
        repaired = extract_code(out)
        return repaired

    def _improve_diff(self, code: str, report: Dict) -> Optional[str]:
        """
        SEARCH/REPLACE patch repair.
        Returns None on failure (patch application failed or broken syntax),
        which triggers a full rewrite on the next round.
        """
        tmpl = self.problem.load_prompt_template("barrier", "improvement_diff.md")
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        prompt = self.problem.render_prompt(
            tmpl, candidate_code=code, eval_report=report_json,
        )
        prompt += "\n\n" + build_diff_format_suffix()
        messages = [
            {"role": "system", "content": "You are a code repair expert. Output only SEARCH/REPLACE modification blocks."},
            {"role": "user", "content": prompt},
        ]
        raw = self.llm.chat(messages, role="barrier")

        def regenerate_fn(current_code: str, retry_note: str) -> str:
            new_prompt = self.problem.render_prompt(
                tmpl, candidate_code=current_code, eval_report=report_json,
            )
            new_prompt += "\n\n" + build_diff_format_suffix()
            if retry_note:
                new_prompt = retry_note + "\n\n" + new_prompt
            msgs = [
                {"role": "system", "content": "You are a code repair expert. Output only SEARCH/REPLACE modification blocks."},
                {"role": "user", "content": new_prompt},
            ]
            return self.llm.chat(msgs, role="barrier")

        patched, total, retry_note = apply_diff_with_retry(
            raw, code, max_retries=config.DIFF_MAX_RETRIES,
            regenerate_fn=regenerate_fn,
        )
        if not patched or total == 0:
            return None
        # syntax gate: drop the result if partial patching broke the syntax
        if _syntax_check(patched) is not None:
            return None
        return patched

    def _verify(self, before: str, after: str, report: Dict) -> Dict:
        tmpl = self.problem.load_prompt_template("barrier", "verification.md")
        prompt = self.problem.render_prompt(
            tmpl, candidate_code=before, repaired_code=after,
            repair_notes=json.dumps(report, ensure_ascii=False)[:1500],
        )
        messages = [
            {"role": "system", "content": "You are a code verification expert. Output strictly in JSON format."},
            {"role": "user", "content": prompt},
        ]
        out = self.llm.chat_json(messages, role="barrier")
        return _extract_json_loose(out)

    @staticmethod
    def _make_forbidden_pattern(candidate: Dict, report: Optional[Dict]) -> Dict:
        """Turn a failure case into a forbidden constraint (to be sedimented into the knowledge base)."""
        err_summary = "unknown"
        if report and report.get("errors"):
            err_summary = "; ".join(
                f"[{e.get('err_type')}] {e.get('description','')[:120]}"
                for e in report["errors"]
            )
        return {
            "type": "forbidden",
            "text": f"Avoid reproducing the following failure pattern: {err_summary}",
            "source": candidate.get("path", ""),
        }


def _extract_json_loose(text: str) -> Dict:
    if not text:
        return {"verdict": "FAIL"}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"verdict": "FAIL"}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"verdict": "FAIL"}


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write(path: str, code: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)


def _write_tmp(code: str) -> str:
    """Write in-memory code to a temp file for subprocess execution."""
    tmp = os.path.join(config.OUTPUTS_DIR, "_tmp_candidate.py")
    _write(tmp, code)
    return tmp


def _resolve_run_path(code: str, path: str) -> str:
    """Ensure the on-disk file matches the in-memory code; return an executable path."""
    if code == _read(path):
        return path
    return _write_tmp(code)

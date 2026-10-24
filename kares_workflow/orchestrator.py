"""
kares_workflow.orchestrator — main closed-loop orchestration for KARES.

Loop: reflection → retrieval → generation → verification (mechanical barrier)
→ diversity screening → evaluation → sedimentation.
Seed: the baseline algorithm (algorithms/baseline/<problem>_soga.py).
"""
import json
import os
import random
import time
from typing import Dict, Optional

from . import config
from .problem_loader import ProblemLoader
from .knowledge_base import KnowledgeBase
from .algorithm_pool import AlgorithmPool
from .diversity_filter import DiversityFilter
from .llm_client import LLMClient
from .dual_reflection import DualReflection
from .coders import get_coder
from .mechanical_barrier import MechanicalBarrier
from .evaluator import evaluate_algorithm
from .knowledge_enrichment_agent import KnowledgeEnrichmentAgent


class KARESOrchestrator:
    """Main closed loop of KARES autonomous algorithm innovation."""

    def __init__(self, problem_name: str = config.DEFAULT_PROBLEM,
                 iterations: int = config.MAX_ITERATIONS,
                 eval_instance_limit: int = config.DEFAULT_EVAL_INSTANCES,
                 seed: int = 42,
                 skip_baseline_eval: bool = False):
        self.problem = ProblemLoader(problem_name)
        self.iterations = iterations
        self.seed = seed
        self.instance_files = self.problem.get_instances(eval_instance_limit)
        if not self.instance_files:
            raise RuntimeError(f"No instance files found for problem '{problem_name}' "
                               f"(pattern={self.problem.instance_pattern}).")

        # run_id isolation: all per-run artifacts go to outputs/run_<timestamp>/ to avoid overwrites
        self.run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        self.run_dir = os.path.join(config.OUTPUTS_DIR, self.run_id)
        config.CANDIDATES_DIR = os.path.join(self.run_dir, "candidates")
        config.CHECKPOINTS_DIR = os.path.join(self.run_dir, "checkpoints")
        config.LOGS_DIR = os.path.join(self.run_dir, "logs")
        config.SEDIMENT_PATH = os.path.join(self.run_dir, "sedimented_knowledge.json")
        config.ensure_output_dirs()

        self.llm = LLMClient()
        self.kb = KnowledgeBase(problem_id=f"P_{problem_name}")
        self.pool = AlgorithmPool()
        self.diversity = DiversityFilter()
        self.reflection = DualReflection(self.llm, self.problem)
        self.generator = get_coder(config.CODE_GEN_MODE)(self.llm, self.problem)
        self.barrier = MechanicalBarrier(self.llm, self.problem)

        # layered exploration: reproducible RNG + stagnation counter
        # (instance fields, read by _step/_build_candidate_plan)
        self.rng = random.Random(self.seed)
        self.no_improve = 0
        self._last_gen_results = []  # for the generation-1 early-stop check in run()

        self.log_path = os.path.join(config.LOGS_DIR, "run.log")
        self._log(f"Run ID: {self.run_id} → {self.run_dir}")
        self._init_baseline(skip_eval=skip_baseline_eval)

    # ---- initialize the baseline seed ----
    def _init_baseline(self, skip_eval: bool = False):
        baseline_path = self.problem.baseline_path
        self._log(f"Baseline algorithm: {baseline_path}")
        if not os.path.exists(baseline_path):
            raise FileNotFoundError(f"Baseline algorithm not found: {baseline_path}")
        with open(baseline_path, "r", encoding="utf-8") as f:
            code = f.read()

        # try reading baseline_fitness from the knowledge graph cache to avoid re-evaluation
        cached_fitness = None
        if self.kb._graph_mode and self.kb.graph is not None:
            p = self.kb.graph._problem_index.get(self.kb.problem_id)
            if p and p.get("baseline_fitness") is not None:
                cached_fitness = p["baseline_fitness"]

        if skip_eval and cached_fitness is not None:
            # skip the evaluation, use the cached fitness
            self._log(f"Skipping baseline evaluation, using cached fitness={cached_fitness:.2f}")
            baseline_fitness = cached_fitness
        elif skip_eval and cached_fitness is None:
            # skip requested but nothing cached: evaluate once
            self._log("Skip requested but no cache available; running one baseline evaluation...")
            res = evaluate_algorithm(baseline_path, self.instance_files, seed=self.seed,
                                     env_scheduler_path=self.problem.env_scheduler_path)
            baseline_fitness = res["mean_fitness"]
            self._log(f"Baseline result: mean_fitness={baseline_fitness:.2f} "
                      f"completed={res['completed']}/{res['total']} std={res['std']:.2f}")
        else:
            # default: evaluate the baseline
            self._log(f"Evaluating baseline ({len(self.instance_files)} instances)...")
            res = evaluate_algorithm(baseline_path, self.instance_files, seed=self.seed,
                                     env_scheduler_path=self.problem.env_scheduler_path)
            baseline_fitness = res["mean_fitness"]
            self._log(f"Baseline result: mean_fitness={baseline_fitness:.2f} "
                      f"completed={res['completed']}/{res['total']} std={res['std']:.2f}")
            if res["errors"]:
                self._log(f"Baseline errors: {res['errors'][:2]}")

        self.pool.seed(baseline_path, code, baseline_fitness,
                       meta={"name": "baseline_soga", "innovation": "single-objective GA baseline"})
        self.diversity.register(code, baseline_path)
        self.best_fitness = baseline_fitness
        self.baseline_fitness = baseline_fitness
        # baseline for vi computation: record it on the graph's problem node
        self.kb.set_baseline(baseline_fitness)
        self.kb.update_problem_best(baseline_fitness)

    # ---- main loop ----
    def run(self) -> Dict:
        self._log("=" * 60)
        self._log(f"KARES loop started | problem={self.problem.problem_name} "
                  f"| instances={len(self.instance_files)} | iterations={self.iterations}")
        self._log("=" * 60)

        no_improve = 0
        self.no_improve = 0
        for gen in range(1, self.iterations + 1):
            self._log(f"\n----- Generation {gen} -----")
            try:
                improved = self._step(gen)
            except Exception as e:
                self._log(f"[Gen {gen}] exception: {repr(e)}")
                improved = False

            # generation-1 early stop: halt and analyze when enough candidates fail to run
            if gen == 1 and config.EARLY_STOP_GEN1_FAILS > 0:
                fail_statuses = {"gen_fail", "barrier_fail", "eval_fail", "exception"}
                failed = [r for r in self._last_gen_results
                          if r.get("status") in fail_statuses]
                if len(failed) >= config.EARLY_STOP_GEN1_FAILS:
                    self._log(f"\n[Early stop] {len(failed)}/{len(self._last_gen_results)} "
                              f"generation-1 candidates failed to run "
                              f"(threshold={config.EARLY_STOP_GEN1_FAILS}); stopping.")
                    self._analyze_gen1_failures(failed)
                    break

            self.pool.record_generation(gen, notes=f"gen{gen}")
            self._checkpoint(gen)

            cur_best = self.pool.best()["fitness"] if self.pool.best() else self.best_fitness
            if cur_best > self.best_fitness + 1e-6:
                self.best_fitness = cur_best
                self.no_improve = 0
                self._log(f"[Gen {gen}] new best: {cur_best:.2f} *")
            else:
                self.no_improve += 1
                self._log(f"[Gen {gen}] no improvement (streak {self.no_improve})")

            if self.no_improve >= config.PATIENCE:
                self._log(f"Early stop: {self.no_improve} consecutive generations without improvement.")
                break

        # end of workflow: enrich the knowledge base (distill this run's new knowledge into the graph)
        self._enrich_knowledge()

        return self._final_report()

    def _step(self, gen: int) -> bool:
        """Run one generation of the closed loop; returns whether any new
        viable candidate was produced.

        Layered candidate scheduling: each generation distributes candidates
        across the exploit/fuse/explore layers; each layer samples parents and
        retrieves knowledge independently, and parent_fitness is passed on vi
        write-back.
        """
        # (1) dual-track reflection (skipped in generation 1: the pool holds
        # only the baseline, so candidates are generated directly from
        # problem-domain knowledge retrieval)
        if gen == 1:
            self._log("[1] Generation 1: generating directly from problem-domain knowledge...")
            refl = {
                "retrieval_query": self.problem.get_direct_query(),
                "improvement_text": "(Generation 1: candidates are generated directly from the problem definition and retrieved knowledge)",
                "horizontal": {}, "vertical": {},
            }
        else:
            self._log("[1] Dual-track reflection...")
            refl = self.reflection.reflect(
                pool_summary=self.pool.top_k_summary(),
                trajectory=self.pool.trajectory_text(),
            )
        self._log(f"    Retrieval query: {refl['retrieval_query'][:120]}...")

        # (2) build the layered candidate plan (stagnation boost decided by self.no_improve)
        adaptive = config.KNOWLEDGE_SELECTION_MODE == "adaptive_rank"
        plan = self._build_candidate_plan()
        layer_counts = {}
        for p in plan:
            layer_counts[p["layer"]] = layer_counts.get(p["layer"], 0) + 1
        self._log(f"[2] Layered candidate plan: {layer_counts} (no_improve={self.no_improve}"
                  f"{', adaptive_rank' if adaptive else ''})")

        # (3) pre-retrieve non-overlapping knowledge groups for the exploit layer
        #     (fuse/explore retrieve on their own; adaptive_rank samples per candidate)
        n_exploit = layer_counts.get("exploit", 0) if not adaptive else 0
        per_cand = config.KNOWLEDGE_PER_CANDIDATE
        exploit_groups: list = []
        if n_exploit > 0:
            exploit_groups = self.kb.retrieve_for_candidates(
                refl["retrieval_query"],
                n_candidates=n_exploit,
                per_candidate=per_cand,
                non_overlap=config.KNOWLEDGE_GROUP_NON_OVERLAP,
            )
        exploit_iter = iter(exploit_groups)
        unique_kids = set()
        for g in exploit_groups:
            unique_kids.update(it.get("node_id") or it["id"] for it in g)
        self._log(f"    exploit pre-retrieved {sum(len(g) for g in exploit_groups)} knowledge "
                  f"entries ({len(unique_kids)} unique).")

        # (4) per-candidate generation, barrier, evaluation and vi write-back
        any_improved = False
        generation_results = []
        n_candidates = len(plan)

        # In-generation snapshot: every candidate of this generation samples
        # parents from the pool snapshot taken at the start of the generation,
        # so they cannot affect each other. In generation 1 the snapshot is
        # [baseline], so all 4 candidates evolve independently from a clean
        # baseline instead of piling onto earlier candidates of the same
        # generation and collapsing into a local optimum. New candidates of
        # this generation still enter the live pool immediately (for diversity
        # screening / best tracking) but never join the parent sampling source
        # — they only become visible to the next generation.
        parent_snapshot = list(self.pool.pool)
        self._log(f"    Parent snapshot: {len(parent_snapshot)} candidates "
                  f"(top={parent_snapshot[0]['fitness']:.2f})" if parent_snapshot else "    Parent snapshot: empty")

        for cidx, layer_cfg in enumerate(plan, 1):
            layer = layer_cfg["layer"]
            parent_mode = layer_cfg["parent_mode"]
            knowledge_mode = layer_cfg["knowledge_mode"]
            self._log(f"\n[3] Generating candidate {cidx}/{n_candidates} [{layer}]...")

            try:
                # sample the parent (from the start-of-generation snapshot; candidates stay independent)
                parent = self.pool.sample_parent(mode=parent_mode, rng=self.rng,
                                                 snapshot=parent_snapshot)
                if parent is None:
                    parent = self.pool.best()
                parent_fitness = parent["fitness"] if parent else self.baseline_fitness
                parent_code = parent["code"] if parent else ""
                parent_name = (parent.get("meta", {}) or {}).get("name", "?") if parent else "?"
                self._log(f"    Parent: {parent_name} (fitness={parent_fitness:.2f}, mode={parent_mode})")
                # retrieve knowledge per layer
                if adaptive:
                    # Eq. (5): stagnation-adaptive offset; s_t = self.no_improve
                    a_t = min(config.ADAPTIVE_A_MAX,
                              config.ADAPTIVE_A_BASE * config.ADAPTIVE_GAMMA ** self.no_improve)
                    kg_items = self.kb.retrieve_adaptive(
                        refl["retrieval_query"], a_t=a_t, rng=self.rng)
                    self._log(f"    Knowledge adaptive_rank a_t={a_t:.2f}, "
                              f"retrieved {len(kg_items)} entries")
                elif knowledge_mode == "single":
                    kg_items = next(exploit_iter, [])
                    self._log(f"    Knowledge mode={knowledge_mode}, retrieved {len(kg_items)} entries")
                elif knowledge_mode == "dual_fuse":
                    kg_items = self.kb.retrieve_dual_for_fusion(refl["retrieval_query"])
                    self._log(f"    Knowledge mode={knowledge_mode}, retrieved {len(kg_items)} entries")
                else:  # random_outside
                    kg_items = self.kb.retrieve_random_outside(
                        refl["retrieval_query"], rng=self.rng,
                        per_candidate=per_cand,
                    )
                    self._log(f"    Knowledge mode={knowledge_mode}, retrieved {len(kg_items)} entries")

                # formatting (the fusion layer uses the fusion format)
                if not adaptive and knowledge_mode == "dual_fuse" and len(kg_items) >= 2:
                    knowledge_text = self.kb.format_knowledge_fusion(kg_items)
                else:
                    knowledge_text = self.kb.format_knowledge(kg_items)
                retrieved_ids = [it.get("node_id") or it["id"] for it in kg_items]

                candidate = self.generator.generate(
                    best_algorithm=parent_code,
                    reflection_text=refl["improvement_text"],
                    knowledge_text=knowledge_text,
                    forbidden_patterns=self.kb.forbidden_patterns_text(),
                    gen=gen,
                    knowledge_ids=retrieved_ids,
                )
                if not candidate:
                    self._log(f"    Candidate {cidx}: generation failed (no code extracted).")
                    generation_results.append({
                        "idx": cidx, "layer": layer, "status": "gen_fail",
                        "knowledge_ids": retrieved_ids, "fitness": None,
                        "parent_fitness": parent_fitness,
                    })
                    continue
                # avoid multiple candidates overwriting the same file: suffix the path with the candidate index
                orig_path = candidate["path"]
                if os.path.exists(orig_path):
                    base, ext = os.path.splitext(orig_path)
                    new_path = f"{base}_c{cidx}{ext}"
                    os.rename(orig_path, new_path)
                    candidate["path"] = new_path

                # borrowed knowledge ids: prefer the subset declared in the
                # candidate header; fall back to the whole retrieved group
                candidate_kids = candidate.get("knowledge_ids") or retrieved_ids
                mode_info = f"[mode={candidate.get('mode', '?')}"
                if candidate.get("fallback_reason"):
                    mode_info += f", fallback: {candidate['fallback_reason']}"
                mode_info += "]"
                self._log(f"    Generated candidate {cidx}: {candidate['name']} "
                          f"(Innovation: {candidate['innovation'][:60]}) {mode_info}")
                self._log(f"    Borrowed knowledge: {candidate_kids}")

                # (4) mechanical barrier (incl. quick evaluation / performance verification)
                self._log(f"    [4] Candidate {cidx} mechanical barrier (quick evaluation on "
                          f"{min(config.BARRIER_QUICK_EVAL_INSTANCES, len(self.instance_files))} instances)...")
                bar = self.barrier.barrier(
                    candidate,
                    seed=self.seed,
                    instance_files=self.instance_files,
                    baseline_fitness=self.baseline_fitness,
                )
                if not bar["passed"]:
                    self._log(f"    Candidate {cidx} failed the barrier ({bar['rounds']} rounds).")
                    self.kb.update_vi(candidate_kids, fitness=0.0, run_id=self.run_id,
                                      gen=gen, success=False, parent_fitness=parent_fitness)
                    self.kb.save_graph(backup=False)
                    if bar.get("forbidden_pattern"):
                        self.kb.sediment(bar["forbidden_pattern"])
                    generation_results.append({
                        "idx": cidx, "layer": layer, "status": "barrier_fail",
                        "knowledge_ids": candidate_kids, "fitness": 0.0,
                        "parent_fitness": parent_fitness,
                    })
                    continue
                qe = bar.get("quick_eval") or {}
                qfit = qe.get("mean_fitness")
                qfit_str = f"quick_fitness={qfit:.2f}" if qfit is not None else "quick_fitness=N/A"
                self._log(f"    Candidate {cidx} passed the barrier ({bar['rounds']} rounds, {qfit_str}).")

                # (5) diversity screening
                self._log(f"    [5] Candidate {cidx} diversity screening...")
                if self.diversity.is_duplicate(bar["code"]):
                    self._log(f"    Candidate {cidx} is a duplicate; skipping.")
                    generation_results.append({
                        "idx": cidx, "layer": layer, "status": "duplicate",
                        "knowledge_ids": candidate_kids, "fitness": None,
                        "parent_fitness": parent_fitness,
                    })
                    continue
                self.diversity.register(bar["code"], bar["path"])

                # (6) evaluation
                self._log(f"    [6] Evaluating candidate {cidx}...")
                res = evaluate_algorithm(bar["path"], self.instance_files, seed=self.seed,
                                         env_scheduler_path=self.problem.env_scheduler_path)
                if not res["ok"]:
                    self._log(f"    Candidate {cidx} evaluation failed: {res['errors'][:2]}")
                    self.kb.update_vi(candidate_kids, fitness=0.0, run_id=self.run_id,
                                      gen=gen, success=False, parent_fitness=parent_fitness)
                    self.kb.save_graph(backup=False)
                    self.kb.sediment({"type": "forbidden",
                                      "text": f"Candidate {cidx} failed on all instances: {res['errors'][:1]}",
                                      "source": bar["path"]})
                    generation_results.append({
                        "idx": cidx, "layer": layer, "status": "eval_fail",
                        "knowledge_ids": candidate_kids, "fitness": 0.0,
                        "parent_fitness": parent_fitness,
                    })
                    continue
                self._log(f"    Candidate {cidx} mean_fitness={res['mean_fitness']:.2f} "
                          f"completed={res['completed']}/{res['total']} std={res['std']:.2f}")

                # vi write-back: evaluation succeeded, pass parent_fitness
                weight = res["completed"] / max(res["total"], 1)
                self.kb.update_vi(candidate_kids, fitness=res["mean_fitness"],
                                  run_id=self.run_id, gen=gen, success=True, weight=weight,
                                  parent_fitness=parent_fitness)
                self.kb.save_graph(backup=False)

                # (7) pool update
                self.pool.update(
                    bar["path"], bar["code"], res["mean_fitness"],
                    mean_fitness=res["mean_fitness"], std=res["std"],
                    meta={"name": candidate["name"],
                          "innovation": candidate["innovation"],
                          "gen": gen,
                          "layer": layer,
                          "parent_fitness": parent_fitness,
                          "knowledge_ids": candidate_kids},
                    gen=gen,
                )
                any_improved = True
                generation_results.append({
                    "idx": cidx, "layer": layer, "status": "success",
                    "name": candidate["name"],
                    "knowledge_ids": candidate_kids,
                    "fitness": res["mean_fitness"],
                    "parent_fitness": parent_fitness,
                })
            except Exception as e:
                # a single candidate's exception must not abort the whole generation
                self._log(f"    Candidate {cidx} exception: {repr(e)}; skipping.")
                generation_results.append({
                    "idx": cidx, "layer": layer, "status": "exception",
                    "knowledge_ids": [], "fitness": None,
                    "parent_fitness": None,
                })

        # (8) knowledge sedimentation for this generation (aggregated for
        #     tracking the effect of individual entries)
        self._last_gen_results = generation_results  # for the early-stop check in run()
        self._log("[8] Knowledge sedimentation...")
        for r in generation_results:
            self.kb.sediment({
                "type": "experience",
                "text": (f"Gen {gen} candidate {r['idx']} [{r['layer']}/{r.get('status')}]: "
                         f"fitness={r.get('fitness')}; "
                         f"parent={r.get('parent_fitness')}; "
                         f"borrowed={r['knowledge_ids']}; "
                         f"bottleneck={refl['horizontal'].get('key_bottleneck','')}"),
                "source": f"gen{gen}",
                "fitness": r.get("fitness"),
                "parent_fitness": r.get("parent_fitness"),
                "knowledge_ids": r["knowledge_ids"],
                "status": r["status"],
                "layer": r["layer"],
            })
        return any_improved

    def _build_candidate_plan(self):
        """Decide the layer mix from self.no_improve and return the layered
        candidate plan. Each item: {layer, parent_mode, knowledge_mode}.
        layer: exploit (single-knowledge exploitation) / fuse (dual-knowledge
        fusion) / explore (random exploration).
        Stagnation boost: when no_improve >= STAGNATION_TRIGGER, explore
        rises to STAGNATION_EXPLORE_RATIO.
        """
        n = config.CANDIDATES_PER_GENERATION
        ratios = dict(config.CANDIDATE_LAYER_RATIOS)

        # stagnation boost (layered mode only; adaptive_rank flattens via a_t instead)
        if config.KNOWLEDGE_SELECTION_MODE != "adaptive_rank" \
                and self.no_improve >= config.STAGNATION_TRIGGER:
            ratios["explore"] = config.STAGNATION_EXPLORE_RATIO
            ratios["exploit"] = max(0.0, 1.0 - ratios["explore"] - ratios.get("fuse", 0.0))
            self._log(f"[Stagnation boost] no_improve={self.no_improve} "
                      f"→ explore={ratios['explore']:.0%}, exploit={ratios['exploit']:.0%}")

        # allocate by ratio (at least 1 exploit; the remainder goes to fuse)
        n_exploit = max(1, round(n * ratios["exploit"]))
        n_explore = round(n * ratios["explore"]) if ratios["explore"] > 0 else 0
        n_fuse = n - n_exploit - n_explore
        if n_fuse < 0:  # ratio overflow: prioritize exploit + explore
            n_exploit = max(1, n - n_explore)
            n_fuse = 0

        plan = (
            [{"layer": "exploit", "parent_mode": "elite",
              "knowledge_mode": "single"}] * n_exploit +
            [{"layer": "fuse", "parent_mode": "elite",
              "knowledge_mode": "dual_fuse"}] * n_fuse +
            [{"layer": "explore", "parent_mode": "random",
              "knowledge_mode": "random_outside"}] * n_explore
        )
        self.rng.shuffle(plan)  # shuffle so the LLM never sees a fixed ordering
        return plan

    # ---- end-of-workflow knowledge enrichment ----
    def _enrich_knowledge(self):
        """Distill this run's new knowledge into the graph via
        KnowledgeEnrichmentAgent. Failures do not halt the workflow."""
        self._log("[9] Knowledge base enrichment...")
        try:
            agent = KnowledgeEnrichmentAgent(self.llm, self.problem, self.kb)
            best = self.pool.best()
            stats = agent.enrich(
                run_id=self.run_id,
                pool_history=self.pool.history,
                baseline_fitness=self.pool.history[0]["best_fitness"] if self.pool.history else None,
                best_fitness=best["fitness"] if best else None,
                iterations_run=len(self.pool.history),
            )
            self._log(f"    Enrichment done: added {stats.get('added', 0)}, "
                      f"skipped {stats.get('skipped', 0)}.")
        except Exception as e:
            self._log(f"    Enrichment failed (non-fatal): {repr(e)}")

    # ---- reporting and persistence ----
    def _analyze_gen1_failures(self, failed: list):
        """Analyze generation-1 failures after the early stop: aggregate by
        type, then re-check each candidate file for syntax/interface issues."""
        import glob as _glob
        import ast as _ast
        from .evaluator import find_scheduler_and_algorithm_classes

        self._log("\n" + "=" * 60)
        self._log("Generation-1 failure analysis")
        self._log("=" * 60)

        # 1. aggregate by failure type
        type_counts = {}
        for r in failed:
            s = r.get("status", "?")
            type_counts[s] = type_counts.get(s, 0) + 1
        self._log(f"Failure type distribution: {type_counts}")
        status_desc = {
            "gen_fail": "LLM produced no extractable code",
            "barrier_fail": "mechanical barrier could not repair it (syntax/interface/runtime/performance)",
            "eval_fail": "passed the barrier but failed the full evaluation",
            "exception": "an exception was raised during processing",
        }
        for s, cnt in type_counts.items():
            self._log(f"  - {s} ({status_desc.get(s, '?')}): {cnt}")

        # 2. layer and borrowed knowledge of each failed candidate
        self._log("\nFailed candidate details:")
        for r in failed:
            self._log(f"  Candidate {r['idx']} [{r['layer']}] status={r['status']} "
                      f"borrowed_knowledge={r.get('knowledge_ids', [])} "
                      f"parent_fitness={r.get('parent_fitness')}")

        # 3. scan the generation-1 candidate files for syntax/interface checks
        gen1_files = sorted(_glob.glob(
            os.path.join(config.CANDIDATES_DIR, "candidate_gen001_*.py")))
        if gen1_files:
            self._log(f"\nGeneration-1 candidate file check ({len(gen1_files)} files):")
            for fp in gen1_files:
                fname = os.path.basename(fp)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        code = f.read()
                    _ast.parse(code)  # syntax check
                    info = find_scheduler_and_algorithm_classes(code)
                    if info and info.get("algorithm"):
                        self._log(f"  [OK] {fname}: syntax OK, "
                                  f"algorithm class={info.get('algorithm')}")
                    else:
                        self._log(f"  [INTERFACE] {fname}: syntax OK but no "
                                  f"contract-compliant scheduler/algorithm class found")
                except SyntaxError as e:
                    self._log(f"  [SYNTAX ERROR] {fname}: line {e.lineno} {e.msg}")
                except Exception as e:
                    self._log(f"  [READ ERROR] {fname}: {repr(e)}")
        else:
            self._log("\nNo generation-1 candidate files found (the LLM may not have produced code).")

        self._log(f"\nFull run log: {self.log_path}")
        self._log("=" * 60)

    def _final_report(self) -> Dict:
        best = self.pool.best()
        report = {
            "problem": self.problem.problem_name,
            "run_id": self.run_id,
            "iterations_run": len(self.pool.history),
            "baseline_fitness": self.pool.history[0]["best_fitness"] if self.pool.history else None,
            "best_fitness": best["fitness"] if best else None,
            "best_path": best["path"] if best else None,
            "best_meta": best["meta"] if best else None,
            "history": self.pool.history,
        }
        report_path = os.path.join(self.run_dir, "final_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        self._log(f"\nFinal best: fitness={report['best_fitness']} path={report['best_path']}")
        self._log(f"Report saved: {report_path}")
        return report

    def _checkpoint(self, gen: int):
        path = os.path.join(config.CHECKPOINTS_DIR, f"checkpoint_gen{gen:03d}.json")
        self.pool.checkpoint(path)

    def _log(self, msg: str):
        print(msg)
        os.makedirs(config.LOGS_DIR, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

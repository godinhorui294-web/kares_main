"""
kares_workflow.knowledge_graph_builder — one-shot migration: build
knowledge_graph.json (nodes + problems + initial edges) from
knowledge_base_unified.json.

Migration strategy:
- one node per paper: K_p_<paper_id> (kind=paper)
- text_for_index: reuse the KnowledgeBase._flatten_paper text
- base_score: LLM scoring preferred (cached by paper_id hash, a one-off
  cost), with a heuristic fallback
- applicable_scenarios: heuristically derived from problem_type_cn /
  algorithm_category
- an initial edge is created for the target problem (vi=base_score, cold start)

Re-runnable: incremental merge; existing experiment data on nodes is never
overwritten (add_node merge semantics).

Usage:
    python -m kares_workflow.knowledge_graph_builder                        # heuristic
    python -m kares_workflow.knowledge_graph_builder --llm-score            # LLM scoring (cached)
    python -m kares_workflow.knowledge_graph_builder --problem uav_firefighting --baseline 5034.28
"""
import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional

from . import config
from .knowledge_graph import KnowledgeGraph, _clamp


# ==================== base_score cache ====================

def _load_cache() -> Dict[str, dict]:
    if not os.path.exists(config.BASE_SCORE_CACHE_PATH):
        return {}
    try:
        with open(config.BASE_SCORE_CACHE_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: Dict[str, dict]):
    os.makedirs(os.path.dirname(config.BASE_SCORE_CACHE_PATH), exist_ok=True)
    with open(config.BASE_SCORE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ==================== heuristic base_score ====================

def heuristic_base_score(paper: Dict) -> tuple:
    """
    Field-completeness heuristic prior (fallback when the LLM is
    unavailable); returns (score, reason). Note: this reflects only how
    complete the structured summary is, not the paper's experimental quality
    or conclusion strength. Scale 0-1: base 0.5 plus bonuses for structural
    completeness and experimental detail.
    """
    l2 = paper.get("layer_2_knowledge_base", {}) or {}
    algo = l2.get("algorithm", {}) or {}
    enc = l2.get("encoding_and_operators", {}) or {}
    pdom = l2.get("problem_domain", {}) or {}

    score = 0.5
    reasons = ["base 0.5"]
    # structural completeness
    if algo.get("core_innovations"):
        n_innov = len(algo.get("core_innovations") or [])
        score += min(0.10, 0.04 * n_innov)  # more innovations -> higher score (anti-degeneracy)
        reasons.append(f"core innovations x{n_innov} (+{min(0.10, 0.04 * n_innov):.2f})")
    if algo.get("algorithm_flow"):
        score += 0.08
        reasons.append("algorithm flow (+0.08)")
    if enc.get("encoding_scheme") or enc.get("crossover_operators") or enc.get("mutation_operators"):
        score += 0.05
        reasons.append("encoding/operator detail (+0.05)")
    if pdom.get("description"):
        score += 0.04
        reasons.append("problem domain description (+0.04)")
    # experimental detail evidence (proxy for the paper's rigor)
    params = l2.get("parameters", {}) or {}
    if isinstance(params, dict) and params:
        score += 0.04
        reasons.append("concrete parameter values (+0.04)")
    if l2.get("fitness_function") or enc.get("fitness_function"):
        score += 0.03
        reasons.append("fitness function definition (+0.03)")
    if l2.get("constraint_handling_details"):
        score += 0.03
        reasons.append("constraint handling detail (+0.03)")
    if paper.get("algorithm_category"):
        score += 0.02
        reasons.append("categorized (+0.02)")
    score = _clamp(score, 0.3, 0.9)
    return score, "field-completeness heuristic (not a paper-quality score): " + "; ".join(reasons)


# ==================== LLM base_score ====================

_LLM_SYS = (
    "You are an expert in assessing the quality of algorithmic knowledge. "
    "Evaluate how valuable this knowledge is for 'scheduling / combinatorial "
    "optimization' problems (0-1 continuous), **basing the assessment "
    "primarily on the paper's experimental results and conclusion strength**.\n"
    "Core criteria (by priority):\n"
    "1. Experimental results: improvement magnitude on benchmarks, number of "
    "baselines compared against, reproducible parameters and results;\n"
    "2. Conclusion strength: whether conclusions are backed by sufficient "
    "experiments, transferability evidence, statistical significance;\n"
    "3. Novelty and actionability: whether operators are clear and reusable, "
    "whether the encoding is well targeted.\n"
    "Suggested ranges:\n"
    "- No explicit experimental data / purely descriptive: 0.40-0.55\n"
    "- Experiments present but mediocre results or a single baseline: 0.55-0.70\n"
    "- Thorough experiments, significant gains, rigorous conclusions: 0.70-0.90\n"
    "- Landmark contributions (field-defining, widely cited): 0.90+\n"
    "Output strictly as JSON: {\"base_score\": 0.xx, \"reason\": \"brief experimental/conclusion evidence\"}."
)


def _paper_brief(paper: Dict) -> str:
    """Build a compact brief for LLM scoring (token-bounded)."""
    l2 = paper.get("layer_2_knowledge_base", {}) or {}
    algo = l2.get("algorithm", {}) or {}
    enc = l2.get("encoding_and_operators", {}) or {}
    pdom = l2.get("problem_domain", {}) or {}
    parts = []
    parts.append(f"Algorithm name: {algo.get('algorithm_name','')}")
    parts.append(f"Category: {paper.get('algorithm_category','')}")
    parts.append(f"Problem domain: {pdom.get('problem_type_cn', pdom.get('problem_type',''))}")
    innov = algo.get("core_innovations", [])
    parts.append("Core innovations: " + ("; ".join(innov[:4]) if innov else "(none)"))
    flow = algo.get("algorithm_flow", [])
    parts.append("Algorithm flow: " + (" -> ".join(flow[:5]) if flow else "(none)"))
    enc_scheme = enc.get("encoding_scheme", [])
    parts.append("Encoding: " + ("; ".join(enc_scheme[:3]) if enc_scheme else "(none)"))
    # experiment-related fields (for the LLM to judge result quality and conclusion strength)
    params = l2.get("parameters", {}) or {}
    if isinstance(params, dict) and params:
        parts.append("Parameter values: " + "; ".join(f"{k}={v}" for k, v in list(params.items())[:5]))
    if l2.get("fitness_function"):
        parts.append("Fitness function: " + str(l2.get("fitness_function"))[:150])
    if l2.get("constraint_handling_details"):
        parts.append("Constraint handling: " + str(l2.get("constraint_handling_details"))[:150])
    l1 = paper.get("layer_1_raw_data", {}) or {}
    if l1.get("title"):
        parts.append("Paper title: " + str(l1.get("title"))[:120])
    return "\n".join(parts)


def llm_base_score(paper: Dict, llm, cache: Dict[str, dict],
                   pid: str) -> tuple:
    """LLM scoring (cached). Falls back to the heuristic on failure."""
    if pid in cache and "base_score" in cache[pid]:
        c = cache[pid]
        return float(c["base_score"]), c.get("reason", "LLM (cached)")

    if llm is None:
        return heuristic_base_score(paper)

    brief = _paper_brief(paper)
    messages = [
        {"role": "system", "content": _LLM_SYS},
        {"role": "user", "content": brief},
    ]
    try:
        out = llm.chat_json(messages, role="reflection")
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            raise ValueError("no JSON found")
        data = json.loads(m.group(0))
        score = _clamp(float(data.get("base_score", 0.5)), 0.0, 1.0)
        reason = data.get("reason", "LLM score")
        cache[pid] = {"base_score": score, "reason": reason}
        return score, reason
    except Exception as e:
        print(f"[builder] LLM scoring failed for {pid} (falling back to heuristic): {e}")
        h_score, h_reason = heuristic_base_score(paper)
        cache[pid] = {"base_score": h_score, "reason": h_reason + " (LLM fallback)"}
        return h_score, h_reason


# ==================== applicable_scenarios heuristic ====================

def heuristic_scenarios(paper: Dict) -> List[str]:
    l2 = paper.get("layer_2_knowledge_base", {}) or {}
    pdom = l2.get("problem_domain", {}) or {}
    cat = paper.get("algorithm_category", "")
    scenarios = []
    pt = pdom.get("problem_type_cn", "") or pdom.get("problem_type", "")
    if pt:
        scenarios.append(pt)
    if cat:
        scenarios.append(cat)
    # dedupe, keep order
    seen, out = set(), []
    for s in scenarios:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


# ==================== main migration ====================

def build_graph_from_unified_kb(
    kg: KnowledgeGraph,
    unified_path: str = config.KB_PATH,
    problem_id: str = "P_uav_firefighting",
    problem_name: str = "uav_firefighting",
    baseline_fitness: Optional[float] = None,
    use_llm: bool = False,
    llm=None,
) -> Dict:
    """
    Migrate the unified KB into the knowledge graph. Returns a stats dict.

    Idempotent: re-running only adds missing nodes; existing experiment data
    is never overwritten.
    """
    if not os.path.exists(unified_path):
        raise FileNotFoundError(f"unified KB not found: {unified_path}")
    with open(unified_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    papers = data.get("papers", []) if isinstance(data, dict) else []

    # ensure the problem node
    kg.ensure_problem(problem_id, name=problem_name, baseline_fitness=baseline_fitness)

    cache = _load_cache()
    # reuse KnowledgeBase._flatten_paper for the flattened text
    from .knowledge_base import KnowledgeBase  # local import to avoid a cycle
    flatten = KnowledgeBase._flatten_paper

    n_new, n_skip, n_llm, n_heur = 0, 0, 0, 0
    for p in papers:
        pid = p.get("paper_id")
        if not pid:
            continue
        nid = f"K_p_{pid}"
        flat = flatten(p) or {}
        text = flat.get("text", "")
        if not text.strip():
            n_skip += 1
            continue

        # base_score
        if use_llm:
            score, reason = llm_base_score(p, llm, cache, pid)
            if "LLM" in reason or "cached" in reason:
                n_llm += 1
            else:
                n_heur += 1
        else:
            score, reason = heuristic_base_score(p)
            n_heur += 1
            cache[pid] = {"base_score": score, "reason": reason}

        node = {
            "node_id": nid,
            "kind": "paper",
            "source": flat.get("source", pid),
            "description": text.split("\n")[0] if text else pid,
            "applicable_scenarios": heuristic_scenarios(p),
            "text_for_index": text,
            "base_score": score,
            "base_score_reason": reason,
            "paper_id": pid,
            "algorithm_name": flat.get("meta", {}).get("algorithm_name", ""),
            "category": p.get("algorithm_category", ""),
        }
        existing = kg.get_node(nid)
        kg.add_node(node)
        if existing is None:
            n_new += 1
        kg.ensure_edge(nid, problem_id)  # cold-start vi=base_score

    if use_llm or cache:
        _save_cache(cache)

    # after a config/formula change, recompute all edges so any remaining
    # experiment_history takes effect under the new policy
    kg.recompute_all_vi()
    kg.save(backup=True)
    return {
        "total_papers": len(papers),
        "new_nodes": n_new,
        "skipped_empty": n_skip,
        "llm_scored": n_llm,
        "heuristic_scored": n_heur,
        "total_nodes": len(kg.knowledge_nodes),
        "total_edges": len(kg.edges),
        "problem_id": problem_id,
    }


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Build the knowledge graph from the unified KB")
    parser.add_argument("--problem", default="uav_firefighting",
                        help="problem name (default uav_firefighting)")
    parser.add_argument("--baseline", type=float, default=None,
                        help="baseline fitness (optional; filled in by the orchestrator at runtime)")
    parser.add_argument("--llm-score", action="store_true",
                        help="score base_score with the LLM (cached, one-off cost)")
    parser.add_argument("--kg-path", default=config.KG_PATH)
    args = parser.parse_args()

    problem_id = f"P_{args.problem}"
    kg = KnowledgeGraph(kg_path=args.kg_path, problem_id=problem_id)

    llm = None
    if args.llm_score:
        from .llm_client import LLMClient
        llm = LLMClient()
        print("[builder] LLM scoring enabled (cached)")

    stats = build_graph_from_unified_kb(
        kg, problem_id=problem_id, problem_name=args.problem,
        baseline_fitness=args.baseline, use_llm=args.llm_score, llm=llm,
    )
    print("\n===== Migration complete =====")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"  graph file: {args.kg_path}")


if __name__ == "__main__":
    main()

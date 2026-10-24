"""
kares_workflow.knowledge_base — knowledge base loading / retrieval / sedimentation.

Internally delegates to KnowledgeGraph (knowledge graph + vi values); the
public interface is unchanged:
  - retrieve(query, top_k) → List[dict]: retrieved entries (graph mode adds node_id / vi)
  - format_knowledge(items) → str: formatted prompt text
  - sediment(entry): sediment experiment experience (graph mode also stores it
    as a retrievable node)
  - forbidden_patterns_text() → str: forbidden constraints built from failure cases

Fallback: when the graph is missing or corrupted, fall back to the legacy
TF-IDF path (unified KB) so the workflow keeps running.

unified KB schema:
  top level: _schema_version / _architecture / papers[]
  paper.layer_2_knowledge_base: { problem_domain, algorithm, encoding_and_operators, ... }
"""
import hashlib
import json
import math
import os
import re
from typing import List, Dict, Any, Optional

from . import config


# ---------- text utilities ----------
# ASCII words as whole tokens, CJK chars as single chars for mixed-language
# retrieval (the knowledge data itself is largely Chinese, and a whole CJK
# sentence must not collapse into one token or cosine similarity would
# degenerate to 0).
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def _tf(tokens: List[str]) -> Dict[str, int]:
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    return tf


def _cosine(tf1: Dict[str, int], tf2: Dict[str, int]) -> float:
    if not tf1 or not tf2:
        return 0.0
    common = set(tf1) & set(tf2)
    if not common:
        return 0.0
    dot = sum(tf1[t] * tf2[t] for t in common)
    n1 = math.sqrt(sum(v * v for v in tf1.values()))
    n2 = math.sqrt(sum(v * v for v in tf2.values()))
    return dot / (n1 * n2) if n1 and n2 else 0.0


class KnowledgeBase:
    """Knowledge base: delegates to KnowledgeGraph; falls back to TF-IDF when the graph is missing."""

    def __init__(self, kb_path: str = config.KB_PATH,
                 kg_path: str = config.KG_PATH,
                 problem_id: Optional[str] = None):
        self.kb_path = kb_path
        self.kg_path = kg_path
        self.problem_id = problem_id or f"P_{config.DEFAULT_PROBLEM}"
        self.baseline_fitness: Optional[float] = None

        self.papers: List[Dict] = []
        self.entries: List[Dict[str, Any]] = []  # retrieval entries {id, text, source, meta}
        self._tf_index: List[Dict[str, int]] = []
        self.sedimented: List[Dict] = []

        # graph mode
        self.graph = None
        self._graph_mode = False
        self._try_load_graph()

        if not self._graph_mode:
            self._load_unified()
        else:
            print(f"[KnowledgeBase] graph mode: {len(self.entries)} nodes "
                  f"(problem={self.problem_id})")
        # make sure the index is ready
        self._tf_index = [_tf(_tokenize(e["text"])) for e in self.entries]

    # ==================== graph loading (with fallback) ====================
    def _try_load_graph(self):
        try:
            from .knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(kg_path=self.kg_path, problem_id=self.problem_id)
        except Exception as e:
            print(f"[KnowledgeBase] graph load failed, falling back to TF-IDF: {e}")
            return
        if not kg.knowledge_nodes:
            print(f"[KnowledgeBase] graph is empty, falling back to TF-IDF ({self.kg_path})")
            return
        self.graph = kg
        self._graph_mode = True
        # build retrieval entries from graph nodes (paper / workflow only, no sediment)
        for n in kg.all_nodes():
            if n.get("kind") == "sediment":
                continue  # sediment logs are not retrievable knowledge
            text = n.get("text_for_index") or n.get("description", "") or ""
            self.entries.append({
                "id": n["node_id"], "text": text,
                "source": n.get("source", ""), "meta": n,
            })
        # sedimented experience is loaded from SEDIMENT_PATH
        # (experiment logs live separately, outside the graph)
        self._load_sedimented()
        # read back the problem baseline
        p = kg._problem_index.get(self.problem_id)
        if p and p.get("baseline_fitness") is not None:
            self.baseline_fitness = p["baseline_fitness"]

    def _load_sedimented(self):
        """Load sedimented experience from SEDIMENT_PATH (used by forbidden_patterns_text across runs)."""
        self.sedimented = []
        if not os.path.exists(config.SEDIMENT_PATH):
            return
        try:
            with open(config.SEDIMENT_PATH, "r", encoding="utf-8") as f:
                self.sedimented = json.load(f)
        except Exception:
            self.sedimented = []

    # ==================== fallback: unified KB ====================
    def _load_unified(self):
        if not os.path.exists(self.kb_path):
            print(f"[KnowledgeBase] warning: knowledge base file not found: {self.kb_path}")
            return
        with open(self.kb_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        self.papers = data.get("papers", []) if isinstance(data, dict) else []
        for p in self.papers:
            entry = self._flatten_paper(p)
            if entry:
                self.entries.append(entry)
        # load sedimented experience
        if os.path.exists(config.SEDIMENT_PATH):
            try:
                with open(config.SEDIMENT_PATH, "r", encoding="utf-8") as f:
                    self.sedimented = json.load(f)
                for s in self.sedimented:
                    self.entries.append({"id": s.get("id", "sediment"),
                                         "text": s.get("text", ""), "source": "experiment",
                                         "meta": s})
            except Exception:
                self.sedimented = []
        print(f"[KnowledgeBase] fallback mode: {len(self.papers)} papers, "
              f"{len(self.sedimented)} sedimented entries.")

    @staticmethod
    def _flatten_paper(paper: Dict) -> Optional[Dict[str, Any]]:
        """Flatten one paper's layer_2/3 knowledge into retrieval text.

        Kept: algorithm structure, operators, encoding, flow, constraint and
        local-search mechanisms, layer_3 heuristic rules.
        Filtered out: scale-level hyperparameters such as population_size /
        max_generations, to avoid unfair competition.
        """
        pid = paper.get("paper_id", "?")
        l2 = paper.get("layer_2_knowledge_base", {}) or {}
        algo = l2.get("algorithm", {}) or {}
        pdom = l2.get("problem_domain", {}) or {}
        enc = l2.get("encoding_and_operators", {}) or {}
        l3 = paper.get("layer_3_rules", {}) or {}

        parts = []
        name = algo.get("algorithm_name", "")
        if name:
            parts.append(f"Algorithm: {name}")
        cat = paper.get("algorithm_category", "")
        if cat:
            parts.append(f"Category: {cat}")
        pt = pdom.get("problem_type_cn", pdom.get("problem_type", ""))
        if pt:
            parts.append(f"Problem domain: {pt}")
        innovations = algo.get("core_innovations", [])
        if innovations:
            parts.append("Core innovations: " + "; ".join(innovations))
        flow = algo.get("algorithm_flow", [])
        if flow:
            parts.append("Algorithm flow: " + " -> ".join(flow))
        enc_scheme = enc.get("encoding_scheme", [])
        if enc_scheme:
            parts.append("Encoding: " + "; ".join(enc_scheme))

        # operators and selection/initialization/local-search mechanisms
        for key in ("selection_mechanism", "crossover_operators", "mutation_operators",
                    "initial_population_strategy", "local_search"):
            val = enc.get(key)
            if val:
                parts.append(f"{key}: {val}")

        # constraint handling, local search, initialization, elitism, fitness
        # function (mechanism descriptions only, no numeric weights)
        for key in ("constraint_handling_details", "local_search_details",
                    "initialization_details", "elitism_details", "fitness_function"):
            val = l2.get(key)
            if val:
                parts.append(f"{key}: {val}")
        # encoding_and_operators may also carry a fitness_function
        if not l2.get("fitness_function") and enc.get("fitness_function"):
            parts.append(f"fitness_function: {enc['fitness_function']}")

        # structural parameters: keep behavioral ones, drop scale-level hyperparameters
        _EXCLUDED_SCALE_PARAMS = {
            "population_size", "max_generations", "max_iterations", "swarm_size",
            "frog_groups", "iter_per_temp", "elite_size", "tournament_size",
            "elite_ratio", "elitism_size", "elitism_rate", "generation_max",
            "stall_generation_max",
        }
        params = l2.get("parameters", {}) or {}
        if isinstance(params, dict):
            filtered = {}
            for k, v in params.items():
                if k in _EXCLUDED_SCALE_PARAMS:
                    continue
                if isinstance(v, dict):
                    continue
                filtered[k] = v
            if filtered:
                parts.append("Parameters: " + "; ".join(f"{k}={v}" for k, v in filtered.items()))

        # layer_3 heuristic rules (parameter_tuning_rules excluded: often carries scale parameters)
        for key in ("derived_heuristics", "encoding_guidelines", "hybrid_strategy_rules"):
            val = l3.get(key)
            if val:
                parts.append(f"{key}: {val}")
        app_rules = l3.get("applicability_rules")
        if app_rules:
            suitable = app_rules.get("suitable_for", [])
            not_suitable = app_rules.get("not_suitable_for", [])
            if suitable:
                parts.append(f"Suitable for: {suitable}")
            if not_suitable:
                parts.append(f"Not suitable for: {not_suitable}")

        # original title as the source
        l1 = paper.get("layer_1_raw_data", {}) or {}
        source = l1.get("title", "") or l1.get("source_file", "") or pid
        text = "\n".join(parts)
        if not text.strip():
            return None
        return {"id": pid, "text": text, "source": source,
                "meta": {"algorithm_name": name, "category": cat, "problem_type": pt}}

    # ==================== retrieval ====================
    def retrieve(self, query: str, top_k: int = config.RETRIEVE_TOP_K,
                 ranking: str = config.RETRIEVE_RANKING,
                 label_filter: Optional[int] = None,
                 min_vi: float = 0.0,
                 problem_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve the top_k knowledge entries.

        Args:
            ranking:
                "joint" (default, sim+solve+vi weighted) / "similarity" (pure TF-IDF)
                / "hybrid" (γ·sim+δ·vi) / "vi" (descending vi)
            label_filter: None = all / +1 = successes only / -1 = failures only /
                0 = no-change only (based on edge.label_stats)
            min_vi: drop knowledge whose vi is below this value
            problem_id: target problem (defaults to self.problem_id)

        Graph mode additionally returns node_id / vi / solve in each result.
        """
        if not self.entries or not query.strip():
            return []
        pid = problem_id or self.problem_id
        q_tf = _tf(_tokenize(query))
        gamma = self.vi_config_gamma if hasattr(self, "vi_config_gamma") else \
            config.VI_CONFIG.get("hybrid_gamma", 0.5)
        delta = config.VI_CONFIG.get("hybrid_delta", 0.5)
        w_sim = config.VI_CONFIG.get("joint_w_sim", 0.4)
        w_solve = config.VI_CONFIG.get("joint_w_solve", 0.3)
        w_vi = config.VI_CONFIG.get("joint_w_vi", 0.3)

        graph_on = self._graph_mode and self.graph is not None
        scored = []  # (sort_key, sim, vi, solve, idx)
        for idx, e_tf in enumerate(self._tf_index):
            sim = _cosine(q_tf, e_tf)
            e = self.entries[idx]
            vi = 0.0
            solve = 0.0
            if graph_on:
                vi = self.graph.get_viability(e["id"], pid)
                solve = self._solve_score(e["id"], pid)
                if vi < min_vi:
                    continue
                if label_filter is not None:
                    edge = self.graph.get_edge(e["id"], pid)
                    if edge is None:
                        continue  # no edge (new problem) → no experiment data
                    stats = edge.get("label_stats", {})
                    pos, neu, neg = stats.get("positive", 0), stats.get("neutral", 0), stats.get("negative", 0)
                    if label_filter == 1 and pos == 0:
                        continue
                    if label_filter == -1 and neg == 0:
                        continue
                    if label_filter == 0 and neu == 0:
                        continue
            # sort key
            if ranking == "vi":
                if not graph_on:
                    continue  # no vi in fallback mode; vi ranking is meaningless
                sort_key = vi
            elif ranking == "hybrid" and graph_on:
                sort_key = gamma * sim + delta * vi
            elif ranking == "joint" and graph_on:
                sort_key = w_sim * sim + w_solve * solve + w_vi * vi
            else:
                sort_key = sim
            # similarity mode requires sim>0; hybrid/vi/joint allow sim=0 with vi/solve
            if ranking == "similarity" and sim <= 0:
                continue
            scored.append((sort_key, sim, vi, solve, idx))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sort_key, sim, vi, solve, idx in scored[:top_k]:
            e = self.entries[idx]
            item = {
                "id": e["id"], "source": e["source"],
                "text": e["text"], "score": round(sim, 4),
                "meta": e.get("meta", {}),
            }
            if graph_on:
                item["node_id"] = e["id"]
                item["vi"] = round(vi, 4)
                item["solve"] = round(solve, 4)
                if ranking in ("hybrid", "joint"):
                    item["hybrid_score"] = round(sort_key, 4)
            results.append(item)
        return results

    def _solve_score(self, node_id: str, problem_id: str) -> float:
        """
        Solve score: experiment success rate of the knowledge on this problem
        (positive / total). No experiment data → 0.0 (cold start relies on
        the sim + vi dimensions).
        """
        if not (self._graph_mode and self.graph is not None):
            return 0.0
        edge = self.graph.get_edge(node_id, problem_id)
        if edge is None:
            return 0.0
        stats = edge.get("label_stats", {})
        pos = stats.get("positive", 0)
        neu = stats.get("neutral", 0)
        neg = stats.get("negative", 0)
        total = pos + neu + neg
        if total == 0:
            return 0.0
        return pos / total

    def format_knowledge(self, items: List[Dict]) -> str:
        """Format retrieval results as text injectable into prompts."""
        if not items:
            return "(no relevant knowledge retrieved)"
        lines = []
        for i, it in enumerate(items, 1):
            tags = []
            if "vi" in it:
                tags.append(f"vi={it['vi']:.2f}")
            if "solve" in it:
                tags.append(f"solve={it['solve']:.2f}")
            tag_str = f" | {' '.join(tags)}" if tags else ""
            lines.append(f"[{i}] Source: {it['source']} (similarity {it['score']}{tag_str})")
            lines.append(it["text"])
            lines.append("")
        return "\n".join(lines)

    def format_knowledge_fusion(self, items: List[Dict]) -> str:
        """Format knowledge text for fusion candidates: builds on the
        format_knowledge output and appends a knowledge-fusion instruction
        block requiring the LLM to fuse the core mechanisms of both entries.
        Falls back to plain format_knowledge output when len(items) < 2.
        """
        base = self.format_knowledge(items)
        if len(items) < 2:
            return base
        fusion_instruction = (
            "\n[Knowledge fusion instructions]\n"
            "Two knowledge entries from different sources are provided below. You must "
            "**fuse the core mechanisms of both** into the generated algorithm, producing "
            "a single coherent new variant rather than picking one or concatenating them. "
            "Specifically:\n"
            "1. Identify the complementary dimensions of the two entries (e.g. one "
            "provides the encoding strategy while the other provides the selection "
            "mechanism; one drives global search while the other strengthens local "
            "refinement).\n"
            "2. Design a unified structure so both entries work together within one "
            "algorithmic framework.\n"
            "3. State the fusion approach and the expected synergy explicitly (1-2 "
            "sentences) in the \"Innovation\" header comment.\n"
            "4. Declare both knowledge node ids in the borrowed-knowledge header: "
            "# Borrowed knowledge: [K_p_xxx, K_p_yyy]"
        )
        return base + fusion_instruction

    def retrieve_for_candidates(self, query: str,
                                n_candidates: int = config.CANDIDATES_PER_GENERATION,
                                per_candidate: int = config.KNOWLEDGE_PER_CANDIDATE,
                                non_overlap: bool = config.KNOWLEDGE_GROUP_NON_OVERLAP,
                                **kwargs) -> List[List[Dict[str, Any]]]:
        """
        Retrieve knowledge entries separately for each candidate of a generation.

        Returns:
            List[List[Dict]]: length n_candidates; each inner list holds the
            entries assigned to that candidate.
        """
        need = n_candidates * per_candidate if non_overlap else max(per_candidate, config.RETRIEVE_TOP_K)
        all_items = self.retrieve(query, top_k=need, **kwargs)
        if not all_items:
            return [[] for _ in range(n_candidates)]

        groups: List[List[Dict]] = []
        if non_overlap:
            for i in range(n_candidates):
                start = i * per_candidate
                end = start + per_candidate
                if start >= len(all_items):
                    # not enough entries: reuse the last group (degraded)
                    groups.append(all_items[-per_candidate:] if all_items else [])
                else:
                    groups.append(all_items[start:end])
        else:
            # sharing allowed: every candidate gets the top entries
            top = all_items[:per_candidate]
            groups = [top.copy() for _ in range(n_candidates)]
        return groups

    # ==================== adaptive probabilistic rank-based selection ====================
    def retrieve_adaptive(self, query: str,
                          n_k: Optional[int] = None,
                          a_t: Optional[float] = None,
                          pool_n: Optional[int] = None,
                          rng=None) -> List[Dict[str, Any]]:
        """Reciprocal-rank sampling without replacement (Eq. 4).

        Rank all eligible entries by the joint score of Eq. (3) (via retrieve),
        then draw n_k entries without replacement, each draw proportional to
        1/(rank + a_t). pool_n caps the ranked window (0/None = full KB).
        The stagnation-adaptive offset a_t is supplied by the caller (Eq. 5).
        """
        import random as _random
        rng = rng or _random.Random()
        n_k = n_k or config.ADAPTIVE_NK
        if pool_n is None:
            pool_n = config.ADAPTIVE_POOL_N
        if not query.strip() or not self.entries:
            return []
        window = pool_n if pool_n and pool_n > 0 else len(self.entries)
        ranked = self.retrieve(query, top_k=window)
        if not ranked:
            return []
        a = config.ADAPTIVE_A_BASE if a_t is None else a_t
        selected: List[Dict[str, Any]] = []
        pool = list(enumerate(ranked, start=1))  # (rank, item)
        for _ in range(min(n_k, len(pool))):
            weights = [1.0 / (rank + a) for rank, _ in pool]
            pick = rng.choices(range(len(pool)), weights=weights, k=1)[0]
            rank, item = pool.pop(pick)
            item = dict(item)
            item["rank"] = rank
            item["a_t"] = round(a, 3)
            selected.append(item)
        return selected

    # ==================== layered exploration retrieval ====================
    def retrieve_dual_for_fusion(self, query: str,
                                 top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve 2 complementary entries for a fusion candidate:
        - 1st: retrieve(query, top_k=1)[0] (most similar)
        - 2nd: from retrieve(query, top_k=top_k+buffer), skip entries whose
          TF-IDF cosine vs. the 1st exceeds DUAL_FUSE_DIVERSITY_CAP and take
          the highest-ranked remaining one (topically related but not redundant)
        Returns at most 2 entries; with fewer than 2 available, returns 1
        (degrades to single-knowledge fusion).
        """
        if not query.strip() or not self.entries:
            return []
        cap = config.DUAL_FUSE_DIVERSITY_CAP
        # fetch a slightly larger pool so the 2nd entry has room to be picked
        pool_k = max(top_k or config.RETRIEVE_TOP_K, 8)
        pool = self.retrieve(query, top_k=pool_k)
        if not pool:
            return []
        first = pool[0]
        if len(pool) < 2:
            return [first]
        first_tf = _tf(_tokenize(first.get("text", "")))
        # highest-ranked entry with similarity < cap vs. the first
        for cand in pool[1:]:
            cand_tf = _tf(_tokenize(cand.get("text", "")))
            sim = _cosine(first_tf, cand_tf)
            if sim < cap:
                return [first, cand]
        # every candidate is too similar to the first → degrade to single knowledge
        return [first]

    def retrieve_random_outside(self, query: str,
                                per_candidate: Optional[int] = None,
                                top_k: Optional[int] = None,
                                pool_mult: Optional[int] = None,
                                rng=None) -> List[Dict[str, Any]]:
        """Random-exploration retrieval: sample per_candidate entries from
        beyond the top-k.
        Implementation: retrieve(query, top_k=base*(1+pool_mult)) to get a
        larger pool, slice [base:] for the "non-top-k" portion, then
        rng.sample per_candidate entries. Reuses the retrieve
        ranking/label_filter/min_vi pathway, so graph mode is not bypassed.
        Falls back to sampling from the full pool (still exploratory) when
        the non-top-k portion is too small.
        """
        import random as _random
        rng = rng or _random.Random()
        per = per_candidate or config.KNOWLEDGE_PER_CANDIDATE
        base_k = top_k or config.RETRIEVE_TOP_K
        mult = pool_mult or config.RANDOM_EXPLORE_POOL_MULT
        # fetch a larger candidate pool
        big_k = max(base_k * (1 + mult), base_k + per * 2)
        big_pool = self.retrieve(query, top_k=int(big_k))
        if not big_pool:
            return []
        # slice off the non-top-k part
        outside = big_pool[base_k:]
        if len(outside) >= per:
            return rng.sample(outside, per)
        # non-top-k too small: sample from the whole big_pool (incl. top-k), still exploratory
        if len(big_pool) >= per:
            return rng.sample(big_pool, per)
        # the pool itself has fewer than per entries → return all of it
        return list(big_pool)

    # ==================== sedimentation ====================
    def sediment(self, entry: Dict):
        """
        Sediment experiment experience / failure cases.
        - type="forbidden": forbidden constraints, persisted to SEDIMENT_PATH
          (accumulate across runs, consumed by forbidden_patterns_text)
        - type="experience": experiment journal, memory only (the raw data
          already lives in experiment_log.jsonl); not added to the graph nor
          written to any global file, to avoid polluting the retrieval space
          and growing SEDIMENT_PATH.
        """
        entry.setdefault("id", "sed_" + hashlib.md5(
            str(entry).encode("utf-8")).hexdigest()[:8])
        self.sedimented.append(entry)
        # only forbidden entries persist; experience stays in memory
        if entry.get("type") != "forbidden":
            return
        try:
            os.makedirs(os.path.dirname(config.SEDIMENT_PATH), exist_ok=True)
            forbidden_only = [s for s in self.sedimented
                              if s.get("type") == "forbidden"]
            with open(config.SEDIMENT_PATH, "w", encoding="utf-8") as f:
                json.dump(forbidden_only, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[KnowledgeBase] failed to write sediment file (ignored): {e}")

    def forbidden_patterns_text(self) -> str:
        """Build forbidden-constraint text from sedimented failure cases for the generation prompt."""
        forbidden = [s for s in self.sedimented if s.get("type") == "forbidden"]
        if not forbidden:
            return "(none)"
        lines = [f"- {f.get('text', '')}" for f in forbidden[-10:]]
        return "\n".join(lines)

    # ==================== vi write-back API (used by the orchestrator) ====================
    def set_baseline(self, fitness: float, problem_id: Optional[str] = None):
        """Record the baseline fitness of the current problem (baseline source for vi computation)."""
        self.baseline_fitness = fitness
        if self._graph_mode and self.graph is not None:
            pid = problem_id or self.problem_id
            self.graph.ensure_problem(pid, baseline_fitness=fitness)

    def update_problem_best(self, fitness: float, problem_id: Optional[str] = None):
        """Update the best-so-far fitness of the problem (best_so_far source for vi)."""
        if self._graph_mode and self.graph is not None:
            pid = problem_id or self.problem_id
            self.graph.update_problem_best(pid, fitness)

    def update_vi(self, knowledge_ids: List[str], fitness: float,
                  run_id: str, gen: int, success: bool = True,
                  weight: float = 1.0, problem_id: Optional[str] = None,
                  parent_fitness: Optional[float] = None):
        """Write experiment results back to the vi values of the involved
        knowledge nodes (called on both the success and failure branches).
        parent_fitness: fitness of the sampled parent; when None, the graph
        internally falls back to the baseline.
        """
        if not knowledge_ids:
            return
        if not self._graph_mode or self.graph is None:
            return
        if self.baseline_fitness is None:
            return  # cannot score without a baseline
        pid = problem_id or self.problem_id
        self.graph.update_vi(
            knowledge_ids=knowledge_ids, problem_id=pid,
            fitness=fitness, baseline=self.baseline_fitness,
            run_id=run_id, gen=gen, success=success, weight=weight,
            parent_fitness=parent_fitness,
        )

    def save_graph(self, backup: bool = False):
        """Explicitly persist the graph (called at orchestrator checkpoints)."""
        if self._graph_mode and self.graph is not None:
            self.graph.save(backup=backup)

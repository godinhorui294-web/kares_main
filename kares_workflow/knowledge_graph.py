"""
kares_workflow.knowledge_graph — knowledge graph: nodes (knowledge entries) +
edges (knowledge↔problem links carrying vi values).

Design (aligned with proposal.md section 3.2):
- nodes: knowledge entries (paper K_p_* / workflow K_w_*), with base_score and
  retrieval text
- edges: (knowledge_id, problem_id) → vi (viability score)
- vi update: exponentially weighted moving average (EWMA, α=0.3)
    * cold start: vi = base_score (estimated by the LLM from the paper's
      experiments and conclusion strength)
    * updated only when success and child_fitness > parent_fitness:
        obs  = (child_fitness - parent_fitness) / |parent_fitness|   (clamped to [-obs_clamp, obs_clamp])
        v_new = α·obs + (1-α)·v_old
- label: +1 improvement / -1 failure / 0 no change; used only for label_stats
  bookkeeping and label_filter retrieval
- raw experiment logs stay out of the graph: they are written to
  outputs/<run_id>/experiment_log.jsonl (per-run archive)
- persistence: utf-8, accumulates across runs; kept outside the per-run
  directory so run_id isolation never wipes it
- robustness: when the graph file is corrupted, KnowledgeBase falls back to
  the legacy TF-IDF path (this class only manages the graph itself)
"""
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import config


# ==================== vi computation ====================

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _label_of(fitness: float, baseline: float, epsilon: float, success: bool) -> int:
    """Experiment label: failure (all evaluations failed / barrier failed) is
    -1; otherwise judged by the relative improvement over the baseline."""
    if not success:
        return -1
    margin = abs(baseline) * epsilon + 1e-9
    if fitness > baseline + margin:
        return 1
    if fitness < baseline - margin:
        return -1
    return 0


class KnowledgeGraph:
    """Knowledge graph: nodes + (knowledge, problem) edges carrying vi values."""

    def __init__(self, kg_path: str = config.KG_PATH,
                 problem_id: Optional[str] = None,
                 vi_config: Optional[Dict] = None):
        self.kg_path = kg_path
        self.problem_id = problem_id
        self.vi_config = dict(config.VI_CONFIG)
        if vi_config:
            self.vi_config.update(vi_config)

        # graph data
        self.problems: List[Dict] = []
        self.knowledge_nodes: List[Dict] = []
        self.edges: List[Dict] = []
        self.meta: Dict[str, Any] = {}

        # indexes
        self._node_index: Dict[str, Dict] = {}                       # node_id -> node
        self._edge_index: Dict[Tuple[str, str], Dict] = {}           # (k_id, p_id) -> edge
        self._problem_index: Dict[str, Dict] = {}                    # problem_id -> problem

        self._load()

    # ==================== load / persist ====================
    def _load(self):
        if not os.path.exists(self.kg_path):
            self.meta = {"_schema_version": "1.0",
                         "_created": datetime.now().isoformat()}
            self._rebuild_index()
            return
        try:
            with open(self.kg_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            # corrupted: don't raise; start empty and let the caller decide on fallback
            print(f"[KnowledgeGraph] warning: graph file corrupted, starting with an empty graph ({e})")
            self.meta = {"_schema_version": "1.0",
                         "_created": datetime.now().isoformat()}
            self._rebuild_index()
            return
        self.problems = data.get("problems", [])
        self.knowledge_nodes = data.get("knowledge_nodes", [])
        self.edges = data.get("edges", [])
        self.meta = data.get("meta", {})
        if not self.meta:
            self.meta = {"_schema_version": data.get("_schema_version", "1.0")}
        self._rebuild_index()

    def _rebuild_index(self):
        self._node_index = {n["node_id"]: n for n in self.knowledge_nodes
                            if "node_id" in n}
        self._problem_index = {p["problem_id"]: p for p in self.problems
                               if "problem_id" in p}
        self._edge_index = {}
        for e in self.edges:
            key = (e.get("knowledge_id"), e.get("problem_id"))
            if key[0] is not None and key[1] is not None:
                self._edge_index[key] = e

    def save(self, path: Optional[str] = None, backup: bool = True):
        """Persist to disk. backup=True first copies the current file into _backups/."""
        path = path or self.kg_path
        if backup and os.path.exists(path):
            try:
                config.ensure_output_dirs()
                ts = time.strftime("%Y%m%d_%H%M%S")
                bak = os.path.join(config.KG_BACKUP_DIR,
                                   f"knowledge_graph_{ts}.json")
                with open(path, "r", encoding="utf-8") as f:
                    with open(bak, "w", encoding="utf-8") as g:
                        g.write(f.read())
            except Exception as e:
                print(f"[KnowledgeGraph] backup failed (ignored): {e}")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.meta["_last_updated"] = datetime.now().isoformat()
        data = {
            "meta": self.meta,
            "problems": self.problems,
            "knowledge_nodes": self.knowledge_nodes,
            "edges": self.edges,
            "vi_config": self.vi_config,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ==================== problem nodes ====================
    def ensure_problem(self, problem_id: str, name: str = "",
                       baseline_fitness: Optional[float] = None) -> Dict:
        """Ensure the problem node exists; baseline_fitness updates keep the better value."""
        p = self._problem_index.get(problem_id)
        if p is None:
            p = {"problem_id": problem_id, "name": name or problem_id,
                 "baseline_fitness": baseline_fitness,
                 "best_fitness_so_far": baseline_fitness}
            self.problems.append(p)
            self._problem_index[problem_id] = p
        else:
            if name:
                p["name"] = name
            if baseline_fitness is not None:
                if p.get("baseline_fitness") is None:
                    p["baseline_fitness"] = baseline_fitness
                if p.get("best_fitness_so_far") is None or \
                        baseline_fitness > p.get("best_fitness_so_far", float("-inf")):
                    p["best_fitness_so_far"] = baseline_fitness
        return p

    def update_problem_best(self, problem_id: str, fitness: float):
        """Update the problem node's best-so-far fitness (best_so_far source for vi)."""
        p = self._problem_index.get(problem_id)
        if p is None:
            return
        cur = p.get("best_fitness_so_far")
        if cur is None or fitness > cur:
            p["best_fitness_so_far"] = fitness

    # ==================== node queries ====================
    def get_node(self, node_id: str) -> Optional[Dict]:
        return self._node_index.get(node_id)

    def all_nodes(self) -> List[Dict]:
        return list(self.knowledge_nodes)

    def add_node(self, node: Dict) -> Dict:
        """Add a node; an existing node_id is merged (base_score is kept
        unless explicitly overwritten)."""
        nid = node.get("node_id")
        if not nid:
            raise ValueError("node must contain node_id")
        existing = self._node_index.get(nid)
        if existing is None:
            self.knowledge_nodes.append(node)
            self._node_index[nid] = node
            return node
        # merge: incoming fields override (base_score only when missing or newly provided)
        for k, v in node.items():
            if k == "base_score":
                if existing.get("base_score") is None and v is not None:
                    existing["base_score"] = v
            else:
                existing[k] = v
        return existing

    # ==================== edges / vi ====================
    def ensure_edge(self, knowledge_id: str, problem_id: str) -> Dict:
        """Ensure the (knowledge_id, problem_id) edge exists; cold-start vi=base_score."""
        key = (knowledge_id, problem_id)
        e = self._edge_index.get(key)
        if e is not None:
            return e
        node = self._node_index.get(knowledge_id)
        base = (node or {}).get("base_score", 0.5)
        cold_start = self.vi_config.get("cold_start_vi", "base_score")
        initial_vi = 0.5 if cold_start == "neutral" else base
        e = {
            "knowledge_id": knowledge_id,
            "problem_id": problem_id,
            "vi": initial_vi,                 # cold start: vi = base_score
            "experiment_count": 0,
            "label_stats": {"positive": 0, "neutral": 0, "negative": 0},
            "last_observation": None,         # last valid observation (when child > parent)
            "last_updated": None,
        }
        self.edges.append(e)
        self._edge_index[key] = e
        return e

    def get_edge(self, knowledge_id: str, problem_id: str) -> Optional[Dict]:
        return self._edge_index.get((knowledge_id, problem_id))

    def get_viability(self, knowledge_id: str, problem_id: Optional[str] = None) -> float:
        """
        Return the vi of the knowledge for the problem. Missing edge/problem →
        fall back to base_score; both missing → 0.5.
        A None problem_id uses self.problem_id.
        """
        pid = problem_id or self.problem_id
        node = self._node_index.get(knowledge_id)
        if pid is None or node is None:
            return (node or {}).get("base_score", 0.5)
        e = self._edge_index.get((knowledge_id, pid))
        if e is None:
            cold_start = self.vi_config.get("cold_start_vi", "base_score")
            return 0.5 if cold_start == "neutral" else node.get("base_score", 0.5)
        return e.get("vi", node.get("base_score", 0.5))

    def update_vi(self, knowledge_ids: List[str], problem_id: str,
                  fitness: float, baseline: float,
                  run_id: str, gen: int,
                  success: bool = True,
                  weight: float = 1.0,
                  timestamp: Optional[str] = None,
                  parent_fitness: Optional[float] = None):
        """
        Write one experiment result back: the raw log goes to a per-run
        sidecar, and the edge gets an incremental EWMA update.

        EWMA update rule (only when success and child_fitness > parent_fitness):
            obs  = (child_fitness - parent_fitness) / |parent_fitness|   (clamped to [-obs_clamp, obs_clamp])
            v_new = α·obs + (1-α)·v_old
        In all other cases (failure / no parent / did not beat the parent),
        vi is left untouched; only experiment_count and label_stats advance.

        Args:
            knowledge_ids: ids of the knowledge nodes actually used by this
              candidate (parsed from the header comment; may be empty)
            weight: experiment confidence weight (mean over instances = 1.0;
              can be adjusted by completed/total)
            parent_fitness: fitness of the sampled parent; the EWMA
              observation baseline
        """
        if not knowledge_ids:
            return
        ts = timestamp or datetime.now().isoformat()
        eps = self.vi_config.get("label_epsilon", 0.01)
        p = self._problem_index.get(problem_id)
        best_so_far = (p or {}).get("best_fitness_so_far", baseline)
        if success and fitness > best_so_far:
            self.update_problem_best(problem_id, fitness)
            best_so_far = fitness

        # raw experiment log goes to the per-run sidecar (not the graph)
        self._append_experiment_log(run_id, {
            "knowledge_ids": list(knowledge_ids),
            "problem_id": problem_id,
            "run_id": run_id, "gen": gen,
            "fitness": fitness, "baseline": baseline,
            "best_so_far": best_so_far,
            "parent_fitness": parent_fitness,
            "success": success, "weight": weight,
            "timestamp": ts,
        })

        alpha = self.vi_config.get("alpha", 0.3)
        obs_clamp = self.vi_config.get("obs_clamp", 1.0)
        improve_mode = self.vi_config.get("improvement_baseline", "parent")

        for kid in knowledge_ids:
            if self._node_index.get(kid) is None:
                continue  # drop invalid ids
            e = self.ensure_edge(kid, problem_id)
            label = _label_of(fitness, baseline, eps, success)
            # accumulate label_stats (counted in all cases)
            lk = {1: "positive", 0: "neutral", -1: "negative"}[label]
            e["label_stats"][lk] = e["label_stats"].get(lk, 0) + 1
            e["experiment_count"] = e.get("experiment_count", 0) + 1

            # EWMA observation: only when success and child > parent
            obs = None
            if success:
                ref = parent_fitness if (improve_mode == "parent"
                                         and parent_fitness is not None) else baseline
                if ref is not None and fitness > ref:
                    denom = abs(ref) if abs(ref) > 1e-9 else 1.0
                    obs = _clamp((fitness - ref) / denom, -obs_clamp, obs_clamp)
                    old_vi = e.get("vi", 0.5)
                    new_vi = _clamp(alpha * obs + (1.0 - alpha) * old_vi, 0.0, 1.0)
                    e["vi"] = new_vi
                    e["last_observation"] = obs
                    e["last_updated"] = ts

    def _append_experiment_log(self, run_id: str, record: Dict):
        """Append the raw experiment log to outputs/<run_id>/experiment_log.jsonl (outside the graph)."""
        if not run_id:
            return
        try:
            log_dir = os.path.join(config.OUTPUTS_DIR, run_id)
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, "experiment_log.jsonl")
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[KnowledgeGraph] failed to write experiment log (ignored): {e}")

    def recompute_all_vi(self):
        """
        Recompute every edge's vi in bulk (after config changes or data
        repairs). Under EWMA: edges still carrying a legacy experiment_history
        are replayed in time order and the history is then dropped; edges
        without history keep their current vi (already incremental).
        """
        for e in self.edges:
            hist = e.get("experiment_history")
            if hist:
                self._replay_history_ewma(e)
            # edges without history: vi is already incremental, keep it

    def _replay_history_ewma(self, edge: Dict):
        """Replay experiment_history in time order with EWMA (α=0.3), update
        vi, then drop the raw history."""
        hist = edge.get("experiment_history", [])
        if not hist:
            return
        node = self._node_index.get(edge["knowledge_id"], {})
        base = node.get("base_score", 0.5)
        cold_start = self.vi_config.get("cold_start_vi", "base_score")
        vi = 0.5 if cold_start == "neutral" else base
        alpha = self.vi_config.get("alpha", 0.3)
        obs_clamp = self.vi_config.get("obs_clamp", 1.0)
        improve_mode = self.vi_config.get("improvement_baseline", "parent")

        # rebuild experiment_count and label_stats from the history
        pos = neu = neg = 0
        last_obs = None
        last_ts = None
        for h in sorted(hist, key=lambda x: x.get("timestamp", "")):
            success = h.get("success", True)
            fitness = h.get("fitness", 0.0)
            baseline = h.get("baseline", 0.0)
            parent = h.get("parent_fitness")
            label = h.get("label")
            if label is None:
                label = _label_of(fitness, baseline,
                                  self.vi_config.get("label_epsilon", 0.01), success)
            if label == 1:
                pos += 1
            elif label == 0:
                neu += 1
            else:
                neg += 1
            # EWMA update
            if success:
                ref = parent if (improve_mode == "parent"
                                 and parent is not None) else baseline
                if ref is not None and fitness > ref:
                    denom = abs(ref) if abs(ref) > 1e-9 else 1.0
                    obs = _clamp((fitness - ref) / denom, -obs_clamp, obs_clamp)
                    vi = _clamp(alpha * obs + (1.0 - alpha) * vi, 0.0, 1.0)
                    last_obs = obs
                    last_ts = h.get("timestamp")
        edge["vi"] = vi
        edge["experiment_count"] = len(hist)
        edge["label_stats"] = {"positive": pos, "neutral": neu, "negative": neg}
        edge["last_observation"] = last_obs
        edge["last_updated"] = last_ts
        # drop the raw history (no longer stored in the graph)
        edge.pop("experiment_history", None)
        edge.pop("experiment_score", None)  # legacy field cleanup

    def strip_sediment_nodes(self) -> int:
        """
        Remove kind=sediment nodes and their edges (experiment logs are not
        knowledge nodes). Returns the number of nodes removed. Sedimented
        experience is kept separately in SEDIMENT_PATH.
        """
        sed_ids = {n["node_id"] for n in self.knowledge_nodes
                   if n.get("kind") == "sediment"}
        if not sed_ids:
            return 0
        before_n = len(self.knowledge_nodes)
        before_e = len(self.edges)
        self.knowledge_nodes = [n for n in self.knowledge_nodes
                                if n.get("kind") != "sediment"]
        self.edges = [e for e in self.edges
                      if e.get("knowledge_id") not in sed_ids]
        self._rebuild_index()
        return before_n - len(self.knowledge_nodes)

    # ==================== new workflow knowledge ====================
    def add_workflow_knowledge(self, description: str, source: str,
                               applicable_scenarios: List[str],
                               base_score: float, reason: str,
                               problem_id: str, run_id: str,
                               text_for_index: Optional[str] = None,
                               kind: str = "workflow") -> str:
        """
        Add a new knowledge node distilled from the workflow and create its
        initial edge to the current problem (vi=base_score).
        node_id = K_w_<run_id>_<hash8>.
        """
        import hashlib
        h = hashlib.md5(description.encode("utf-8")).hexdigest()[:8]
        nid = f"K_w_{run_id}_{h}"
        node = {
            "node_id": nid,
            "kind": kind,
            "source": source,
            "description": description,
            "applicable_scenarios": applicable_scenarios or [],
            "text_for_index": text_for_index or description,
            "base_score": _clamp(float(base_score), 0.0, 1.0),
            "base_score_reason": reason,
            "created_run_id": run_id,
            "created_at": datetime.now().isoformat(),
        }
        self.add_node(node)
        self.ensure_edge(nid, problem_id)
        return nid

    # ==================== retrieval helpers ====================
    def iter_edges_for_problem(self, problem_id: str) -> List[Dict]:
        return [e for e in self.edges if e.get("problem_id") == problem_id]

    def __repr__(self):
        return (f"KnowledgeGraph(nodes={len(self.knowledge_nodes)}, "
                f"edges={len(self.edges)}, problems={len(self.problems)})")

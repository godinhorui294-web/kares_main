"""
kares_workflow.algorithm_pool — candidate algorithm pool and cross-generation
best-history tracking.

Each pool item: {path, code, fitness, mean_fitness, std, meta, gen}
History: per-generation best {gen, best_fitness, path, notes}
"""
import json
import os
import random
from typing import List, Dict, Optional

from . import config


class AlgorithmPool:
    """Maintains the candidate algorithm pool and the evolution history."""

    def __init__(self, pool_size: int = config.POOL_SIZE):
        self.pool_size = pool_size
        self.pool: List[Dict] = []      # fitness-descending
        self.history: List[Dict] = []   # per-generation best trajectory

    # ---- pool operations ----
    def seed(self, path: str, code: str, fitness: float, meta: Optional[Dict] = None):
        """Inject the initial seed (baseline)."""
        self.pool.append({
            "path": path, "code": code, "fitness": fitness,
            "mean_fitness": fitness, "std": 0.0,
            "meta": meta or {"name": "baseline"}, "gen": 0,
        })
        self._sort()

    def update(self, path: str, code: str, fitness: float,
               mean_fitness: float = 0.0, std: float = 0.0,
               meta: Optional[Dict] = None, gen: int = 0):
        """Add a new candidate and prune to capacity."""
        self.pool.append({
            "path": path, "code": code, "fitness": fitness,
            "mean_fitness": mean_fitness or fitness, "std": std,
            "meta": meta or {}, "gen": gen,
        })
        self._sort()
        self.prune()

    def _sort(self):
        self.pool.sort(key=lambda x: x.get("fitness", float("-inf")), reverse=True)

    def prune(self):
        if len(self.pool) > self.pool_size:
            self.pool = self.pool[: self.pool_size]

    def best(self) -> Optional[Dict]:
        return self.pool[0] if self.pool else None

    # ---- parent sampling (for layered exploration) ----
    def elite(self, k: int = None) -> List[Dict]:
        """Return the top-k candidates (fitness-descending shallow copy; the
        pool is left untouched). k defaults to config.ELITE_POOL_SIZE;
        returns everything when the pool is smaller."""
        k = k or config.ELITE_POOL_SIZE
        k = min(k, len(self.pool))
        return list(self.pool[:k])

    def sample_parent(self, mode: str = "best",
                      rng: Optional[random.Random] = None,
                      snapshot: Optional[List[Dict]] = None) -> Optional[Dict]:
        """Sample one parent by strategy.

        mode='best'    → pool[0] (legacy behavior)
        mode='elite'   → uniform sample from the top ELITE_POOL_SIZE (exploit/fuse layers)
        mode='random'  → uniform sample from the whole pool (explore layer)
        rng is optional (reproducibility); returns None on an empty pool;
        a pool of length 1 always returns pool[0] regardless of mode.

        snapshot: an in-generation snapshot (shallow copy of the pool at the
                  start of the generation). When given, parents are sampled
                  from the snapshot so the candidates of one generation stay
                  independent (all see the start-of-generation pool) instead
                  of later candidates standing on the shoulders of earlier
                  ones, which would weaken diversity. When omitted, sampling
                  uses the live pool (legacy behavior).
        """
        src = snapshot if snapshot is not None else self.pool
        if not src:
            return None
        if len(src) == 1 or mode == "best":
            return src[0]
        rng = rng or random.Random()
        if mode == "elite":
            k = min(config.ELITE_POOL_SIZE, len(src))
            candidates = list(src[:k])
        else:  # "random" or unknown values
            candidates = list(src)
        return rng.choice(candidates)

    def top_k_summary(self, k: int = 5) -> str:
        """Build a pool summary for the horizontal-reflection prompt."""
        if not self.pool:
            return "(empty pool)"
        lines = []
        for i, item in enumerate(self.pool[:k], 1):
            meta = item.get("meta", {})
            name = meta.get("name", os.path.basename(item.get("path", "")))
            lines.append(
                f"#{i} fitness={item['fitness']:.2f} mean={item.get('mean_fitness',0):.2f} "
                f"std={item.get('std',0):.2f} name={name} gen={item.get('gen',0)}"
            )
            innov = meta.get("innovation", "")
            if innov:
                lines.append(f"    Innovation: {innov}")
            kids = meta.get("knowledge_ids", [])
            if kids:
                lines.append(f"    Borrowed knowledge: {kids}")
        return "\n".join(lines)

    # ---- history trajectory ----
    def record_generation(self, gen: int, notes: str = ""):
        b = self.best()
        self.history.append({
            "gen": gen,
            "best_fitness": b["fitness"] if b else None,
            "path": b["path"] if b else None,
            "notes": notes,
        })

    def trajectory_text(self, window: int = config.REFLECTION_WINDOW) -> str:
        """Build the cross-generation best-fitness trajectory for the vertical-reflection prompt."""
        if not self.history:
            return "(no history)"
        recent = self.history[-window:]
        lines = []
        for h in recent:
            lines.append(f"Gen {h['gen']}: best_fitness={h['best_fitness']}")
            if h.get("notes"):
                lines.append(f"    {h['notes']}")
        return "\n".join(lines)

    # ---- persistence ----
    def checkpoint(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = {
            "pool": [{k: v for k, v in item.items() if k != "code"} for item in self.pool],
            "history": self.history,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def __len__(self):
        return len(self.pool)

"""
kares_workflow.knowledge_enrichment_agent — enrich the knowledge base at the
end of a workflow run.

Distills new knowledge entries — absent from the current knowledge base —
from this run's evolutionary trajectory, key innovations and failure
lessons; adds them to the graph as K_w_<run_id>_<hash> nodes with an initial
edge to the current problem (vi=base_score).

- inputs: pool history, best/failure lessons, a summary of existing knowledge
  nodes (dedupe reference)
- the LLM produces a JSON array: [{description, source, applicable_scenarios,
  base_score, reason}]
- dedupe: entries whose TF-IDF cosine similarity to an existing node exceeds
  ENRICH_SIMILARITY_CAP are dropped
- added to the graph and persisted (with backup)
- robust: LLM/JSON failures skip enrichment without halting the workflow
"""
import json
import os
import re
from typing import Dict, List, Optional

from . import config
from .knowledge_base import KnowledgeBase, _tokenize, _tf, _cosine
from .llm_client import LLMClient
from .problem_loader import ProblemLoader


def _extract_json_array(text: str) -> Optional[List[Dict]]:
    """Extract a JSON array from LLM output (tolerates ```json fences and surrounding prose)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return None


class KnowledgeEnrichmentAgent:
    """Agent that enriches the knowledge base after a workflow run."""

    def __init__(self, llm: LLMClient, problem: ProblemLoader,
                 kb: KnowledgeBase):
        self.llm = llm
        self.problem = problem
        self.kb = kb

    def enrich(self, run_id: str, pool_history: List[Dict],
               baseline_fitness: Optional[float],
               best_fitness: Optional[float],
               iterations_run: int,
               lessons: str = "") -> Dict:
        """
        Run knowledge enrichment. Returns a stats dict.
        Graph mode only; skipped entirely in fallback mode.
        """
        if not self.kb._graph_mode or self.kb.graph is None:
            print("[Enrichment] fallback mode, skipping")
            return {"added": 0, "skipped": 0, "mode": "fallback"}

        problem_id = self.kb.problem_id
        trajectory = self._format_trajectory(pool_history)
        if not lessons:
            lessons = self._derive_lessons(pool_history)
        existing_summary = self._existing_summary(limit=40)

        tmpl = self.problem.load_prompt_template("enrichment", "knowledge_enrichment.md")
        prompt = self.problem.render_prompt(
            tmpl,
            problem_name=self.problem.problem_name,
            baseline_fitness=baseline_fitness,
            best_fitness=best_fitness,
            iterations_run=iterations_run,
            trajectory=trajectory,
            lessons=lessons,
            existing_summary=existing_summary,
            run_id=run_id,
        )
        messages = [
            {"role": "system",
             "content": "You are an expert in distilling algorithmic knowledge. Output strictly as a JSON array with no extra text."},
            {"role": "user", "content": prompt},
        ]
        try:
            out = self.llm.chat_json(messages, role="reflection")
        except Exception as e:
            print(f"[Enrichment] LLM call failed, skipping: {e}")
            return {"added": 0, "skipped": 0, "error": str(e)}

        new_items = _extract_json_array(out) or []
        added, skipped = 0, 0
        added_ids: List[str] = []
        for item in new_items:
            desc = (item.get("description") or "").strip()
            if not desc:
                skipped += 1
                continue
            # dedupe: TF-IDF similarity against existing nodes
            if self._is_duplicate(desc):
                skipped += 1
                continue
            base_score = item.get("base_score", 0.5)
            try:
                base_score = float(base_score)
            except Exception:
                base_score = 0.5
            nid = self.kb.graph.add_workflow_knowledge(
                description=desc,
                source=item.get("source", f"{run_id} experimental observation"),
                applicable_scenarios=item.get("applicable_scenarios", []) or [],
                base_score=base_score,
                reason=item.get("reason", ""),
                problem_id=problem_id,
                run_id=run_id,
            )
            added_ids.append(nid)
            added += 1

        # persist (with backup)
        if added > 0:
            self.kb.graph.save(backup=True)
            # sync into kb.entries so retrieval sees them by the end of this
            # run (usually the run is already over by then)
            for nid in added_ids:
                node = self.kb.graph.get_node(nid)
                if node:
                    self.kb.entries.append({
                        "id": nid,
                        "text": node.get("text_for_index") or node.get("description", ""),
                        "source": node.get("source", ""),
                        "meta": node,
                    })
                    self.kb._tf_index.append(_tf(_tokenize(
                        node.get("text_for_index") or node.get("description", ""))))

        # archive into the run directory
        self._archive(run_id, new_items, added_ids)
        print(f"[Enrichment] added {added} knowledge entries, skipped {skipped} (duplicates/empty)")
        return {"added": added, "skipped": skipped, "added_ids": added_ids,
                "total_candidates": len(new_items)}

    # ---- helpers ----
    def _format_trajectory(self, history: List[Dict]) -> str:
        if not history:
            return "(no evolutionary trajectory)"
        lines = []
        for h in history:
            lines.append(f"Gen {h.get('gen')}: best_fitness={h.get('best_fitness')}")
            notes = h.get("notes", "")
            if notes:
                lines.append(f"    {notes}")
        return "\n".join(lines)

    def _derive_lessons(self, history: List[Dict]) -> str:
        """Summarize lessons from sedimented experience."""
        exps = [s for s in self.kb.sedimented if s.get("type") == "experience"]
        forbids = [s for s in self.kb.sedimented if s.get("type") == "forbidden"]
        parts = []
        if exps:
            parts.append("[Success/experiment experience]")
            for e in exps[-8:]:
                parts.append(f"- {e.get('text', '')[:200]}")
        if forbids:
            parts.append("\n[Failure lessons]")
            for f in forbids[-6:]:
                parts.append(f"- {f.get('text', '')[:200]}")
        return "\n".join(parts) if parts else "(no notable lessons)"

    def _existing_summary(self, limit: int = 40) -> str:
        """Summary of existing knowledge nodes (dedupe reference)."""
        nodes = self.kb.graph.all_nodes()
        # prefer paper nodes
        papers = [n for n in nodes if n.get("kind") == "paper"][:limit]
        lines = []
        for n in papers:
            desc = (n.get("description") or n.get("text_for_index", ""))[:120]
            lines.append(f"- [{n['node_id']}] {desc}")
        return "\n".join(lines) if lines else "(knowledge base is empty)"

    def _is_duplicate(self, desc: str) -> bool:
        """Duplicate when the TF-IDF cosine similarity to an existing node exceeds ENRICH_SIMILARITY_CAP."""
        cap = config.ENRICH_SIMILARITY_CAP
        q_tf = _tf(_tokenize(desc))
        if not q_tf:
            return False
        for e_tf in self.kb._tf_index:
            if _cosine(q_tf, e_tf) > cap:
                return True
        return False

    def _archive(self, run_id: str, items: List[Dict], added_ids: List[str]):
        """Archive into the run directory under enrichment/."""
        if not hasattr(self.kb, 'graph') or self.kb.graph is None:
            return
        try:
            archive_dir = os.path.join(config.OUTPUTS_DIR, run_id, "enrichment")
            os.makedirs(archive_dir, exist_ok=True)
            archive = [{"node_id": nid, **item}
                       for nid, item in zip(added_ids, items[:len(added_ids)])]
            path = os.path.join(archive_dir, "new_knowledge.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(archive, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Enrichment] archive failed (ignored): {e}")

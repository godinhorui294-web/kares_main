"""
kares_workflow.dual_reflection — dual-track reflection (horizontal + vertical).

Horizontal reflection: structured comparison within the same generation's
algorithm pool → features to preserve / defects to avoid / improvement
suggestions.
Vertical reflection: tracking the cross-generation best-fitness trajectory
→ persistent features / leap causes / breakthrough directions.

Output synthesis: the retrieval query (for knowledge_base.retrieve) plus an
improvement-directions text (injected into the generation prompt).
"""
import json
import re
from typing import Dict, Optional

from . import config
from .llm_client import LLMClient
from .problem_loader import ProblemLoader


def _extract_json(text: str) -> Optional[Dict]:
    """Extract a JSON object from LLM output (tolerates surrounding prose and code fences)."""
    if not text:
        return None
    # strip ```json ... ``` fences
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # find the first {...}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        # tolerate trailing commas etc.: try truncating step by step
        s = m.group(0)
        for end in range(len(s), 0, -1):
            try:
                return json.loads(s[:end])
            except Exception:
                continue
        return None


class DualReflection:
    """Dual-track reflection: horizontal + vertical."""

    def __init__(self, llm: LLMClient, problem: ProblemLoader):
        self.llm = llm
        self.problem = problem

    def reflect(self, pool_summary: str, trajectory: str,
                window: int = config.REFLECTION_WINDOW) -> Dict:
        """Run dual-track reflection; returns {horizontal, vertical, retrieval_query, improvement_text}."""
        horizontal = self._horizontal(pool_summary)
        vertical = self._vertical(trajectory, window)
        retrieval_query = self._build_query(horizontal, vertical)
        improvement_text = self._format_improvement(horizontal, vertical)
        return {
            "horizontal": horizontal,
            "vertical": vertical,
            "retrieval_query": retrieval_query,
            "improvement_text": improvement_text,
        }

    def _horizontal(self, pool_summary: str) -> Dict:
        tmpl = self.problem.load_prompt_template("reflection", "horizontal_reflection.md")
        prompt = self.problem.render_prompt(tmpl, pool_summary=pool_summary)
        messages = [
            {"role": "system", "content": "You are an expert in the reflective analysis of scheduling algorithms. Output strictly in JSON format."},
            {"role": "user", "content": prompt},
        ]
        out = self.llm.chat_json(messages, role="reflection")
        data = _extract_json(out) or {}
        if not data:
            data = {"preserve_features": [], "avoid_defects": [],
                    "improvement_suggestions": ["(reflection parsing failed; keep the current structure and fine-tune the operators)"],
                    "key_bottleneck": "unknown"}
        return data

    def _vertical(self, trajectory: str, window: int) -> Dict:
        if not trajectory or trajectory == "(no history)":
            return {"persistent_features": [], "leap_causes": [],
                    "stagnation_reason": "first run, no historical trajectory",
                    "next_breakthrough_direction": "focus the first iteration on establishing a feasible-solution baseline"}
        tmpl = self.problem.load_prompt_template("reflection", "vertical_reflection.md")
        prompt = self.problem.render_prompt(tmpl, window=window, history_trajectory=trajectory)
        messages = [
            {"role": "system", "content": "You are an expert in analyzing the evolutionary trajectories of scheduling algorithms. Output strictly in JSON format."},
            {"role": "user", "content": prompt},
        ]
        out = self.llm.chat_json(messages, role="reflection")
        data = _extract_json(out) or {}
        if not data:
            data = {"persistent_features": [], "leap_causes": [],
                    "stagnation_reason": "reflection parsing failed", "next_breakthrough_direction": "unknown"}
        return data

    def _build_query(self, horizontal: Dict, vertical: Dict) -> str:
        """Synthesize the knowledge retrieval query."""
        parts = []
        hb = horizontal.get("key_bottleneck", "")
        if hb:
            parts.append(f"Core bottleneck: {hb}")
        parts.append("Improvement directions: " + "; ".join(horizontal.get("improvement_suggestions", [])))
        nd = vertical.get("next_breakthrough_direction", "")
        if nd:
            parts.append(f"Breakthrough direction: {nd}")
        parts.append("scheduling algorithm combinatorial optimization metaheuristic "
                     "crossover mutation selection constraint handling encoding")
        return "\n".join(parts)

    @staticmethod
    def _format_improvement(horizontal: Dict, vertical: Dict) -> str:
        """Format the improvement-directions text injected into the generation prompt."""
        lines = ["[Horizontal reflection]"]
        lines.append("Features to preserve: " + "; ".join(horizontal.get("preserve_features", [])))
        lines.append("Defects to avoid: " + "; ".join(horizontal.get("avoid_defects", [])))
        lines.append("Improvement suggestions: " + "; ".join(horizontal.get("improvement_suggestions", [])))
        lines.append("Core bottleneck: " + horizontal.get("key_bottleneck", "unknown"))
        lines.append("")
        lines.append("[Vertical reflection]")
        lines.append("Persistent features: " + "; ".join(vertical.get("persistent_features", [])))
        lines.append("Next breakthrough direction: " + vertical.get("next_breakthrough_direction", "unknown"))
        if vertical.get("stagnation_reason"):
            lines.append("Stagnation reason: " + vertical.get("stagnation_reason"))
        return "\n".join(lines)

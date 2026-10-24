"""base_coder — single-shot full-code generation (fallback mode).

Simplest generation strategy: one LLM call produces the plan plus the complete
code block. Serves as the fallback when diff mode fails, and as the default
path when best_algorithm is empty. Logic migrated from CodeGenerator in the
original code_generator.py.
"""
import os
from typing import Optional

from .. import config
from ..llm_client import LLMClient
from ..problem_loader import ProblemLoader
from ._utils import extract_code, _parse_header


class BaseCoder:
    """Single-shot full-code generator (fallback)."""

    def __init__(self, llm: LLMClient, problem: ProblemLoader):
        self.llm = llm
        self.problem = problem

    def generate(self, *, best_algorithm: str, reflection_text: str,
                 knowledge_text: str, forbidden_patterns: str,
                 gen: int,
                 knowledge_ids: list = None) -> Optional[dict]:
        """
        Generate a candidate algorithm in a single full-code shot.

        Args:
            knowledge_ids: ids of retrieved knowledge nodes (injected into the
                prompt so the LLM can declare what it borrows)

        Returns: {path, code, name, innovation, raw, mode, fallback_reason,
                  knowledge_ids} or None.
        """
        system_tmpl = self.problem.load_prompt_template("system", "system_prompt.md")
        system_prompt = self.problem.render_prompt(
            system_tmpl, forbidden_patterns=forbidden_patterns
        )
        gen_tmpl = self.problem.load_prompt_template("generation", "algorithm_generation.md")
        user_prompt = self.problem.render_prompt(
            gen_tmpl,
            best_algorithm=best_algorithm or "# (no previous algorithm; design from scratch)",
            reflection=reflection_text,
            knowledge=knowledge_text,
            forbidden_patterns=forbidden_patterns,
            knowledge_ids=_format_knowledge_ids(knowledge_ids),
        )

        # Extra code-block format hints only apply in fallback mode; never
        # append them in diff mode, where they would break SEARCH/REPLACE output.

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw = self.llm.chat(messages, role="generation")

        # Robust code extraction: try a looser match before giving up.
        code = extract_code(raw)
        if not code:
            import re
            # try any fenced code block
            m = re.search(r"```.*?\n(.*?)```", raw, re.DOTALL)
            if m:
                code = m.group(1).strip()
            # last resort: the text is mostly code, take everything from the
            # first class definition onward
            elif "class " in raw and "def " in raw:
                class_pos = raw.find("class ")
                if class_pos >= 0:
                    code = raw[class_pos:].strip()

        if not code:
            return None

        name, innovation, declared_ids = _parse_header(code)
        path = os.path.join(config.CANDIDATES_DIR, f"candidate_gen{gen:03d}_{name}.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        # Borrowed knowledge ids: prefer the subset declared in the code header;
        # fall back to the full retrieval set when nothing is declared.
        return {"path": path, "code": code, "name": name,
                "innovation": innovation, "raw": raw,
                "mode": "base", "fallback_reason": None,
                "knowledge_ids": declared_ids or list(knowledge_ids or [])}


def _format_knowledge_ids(knowledge_ids) -> str:
    """Format the knowledge id list as prompt placeholder text."""
    if not knowledge_ids:
        return "(no knowledge nodes retrieved for this run)"
    return ", ".join(knowledge_ids)

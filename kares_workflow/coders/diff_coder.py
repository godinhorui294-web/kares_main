"""diff_coder — SEARCH/REPLACE incremental generation (primary mode).

The LLM emits only SEARCH/REPLACE patches, which are applied on top of the
previous generation's best algorithm. Falls back internally to BaseCoder on
failure (empty base / patch application failure).

Key design points:
1. Empty or very short best_algorithm -> immediate base fallback (diff cannot
   patch empty code)
2. The LLM output is SEARCH/REPLACE text (not a ```python block), so it skips
   extract_code and goes straight to apply_diff_with_retry
3. The regenerate_fn closure re-renders the prompt with current_code (already
   partially applied); otherwise the LLM would see stale code and its SEARCH
   blocks could never match
4. The prompt explicitly asks for the header comment (algorithm name /
   innovation) to be updated via SEARCH/REPLACE; _parse_header runs again on
   the patched code
5. patched is None or total_applied == 0 -> total failure, fall back to base;
   patched and total_applied > 0 -> success (partial success counts; retry_note
   records it but no fallback happens)
6. Diff format instructions are injected dynamically via
   build_diff_format_suffix(); templates carry only business content
"""
import os
from typing import Optional

from .. import config
from ..llm_client import LLMClient
from ..problem_loader import ProblemLoader
from ._utils import _parse_header
from .base_coder import BaseCoder, _format_knowledge_ids
from .apply import apply_diff_with_retry
from .diff_prompts import build_diff_format_suffix


# best_algorithm shorter than this is treated as unusable; fall back to base
# (diff cannot patch very short code)
_MIN_BASE_LEN = 200


class DiffCoder:
    """SEARCH/REPLACE incremental generator (primary mode)."""

    def __init__(self, llm: LLMClient, problem: ProblemLoader,
                 max_retries: int = None):
        self.llm = llm
        self.problem = problem
        self.max_retries = max_retries if max_retries is not None else config.DIFF_MAX_RETRIES
        self.base_coder = BaseCoder(llm, problem)  # internal fallback

    def generate(self, *, best_algorithm: str, reflection_text: str,
                 knowledge_text: str, forbidden_patterns: str,
                 gen: int,
                 knowledge_ids: list = None) -> Optional[dict]:
        """
        Generate a candidate algorithm incrementally via SEARCH/REPLACE.

        Args:
            knowledge_ids: ids of retrieved knowledge nodes (injected into the
                prompt so the LLM can declare what it borrows)

        Returns: {path, code, name, innovation, raw, mode, fallback_reason,
                  knowledge_ids} or None.
        """
        # Edge case 1: empty/short best_algorithm -> base fallback
        if not best_algorithm or len(best_algorithm) < _MIN_BASE_LEN:
            result = self.base_coder.generate(
                best_algorithm=best_algorithm, reflection_text=reflection_text,
                knowledge_text=knowledge_text, forbidden_patterns=forbidden_patterns,
                gen=gen, knowledge_ids=knowledge_ids,
            )
            if result is None:
                return None
            result["mode"] = "base"
            result["fallback_reason"] = "empty_or_too_short_base"
            return result

        # Assemble system + diff generation templates
        system_tmpl = self.problem.load_prompt_template("system", "system_prompt.md")
        system_prompt = self.problem.render_prompt(
            system_tmpl, forbidden_patterns=forbidden_patterns
        )
        gen_tmpl = self.problem.load_prompt_template("generation", "algorithm_generation_diff.md")
        user_prompt = self.problem.render_prompt(
            gen_tmpl,
            best_algorithm=best_algorithm,
            reflection=reflection_text,
            knowledge=knowledge_text,
            forbidden_patterns=forbidden_patterns,
            knowledge_ids=_format_knowledge_ids(knowledge_ids),
        )
        # Inject diff format instructions dynamically
        user_prompt += "\n\n" + build_diff_format_suffix()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw_diff = self.llm.chat(messages, role="generation")

        # ---- Pre-check: empty or non-diff LLM output -> try extracting full code ----
        import re, logging as _logging
        from ._utils import extract_code
        _logger = _logging.getLogger("kares")
        has_diff_format = raw_diff and (
            "<<<<<<< SEARCH" in raw_diff
            or "<<<<<<<" in raw_diff
            or re.search(r"^SEARCH\s*\n", raw_diff, re.MULTILINE)
        )

        if not has_diff_format:
            if raw_diff:
                # LLM produced content but not in diff format -> try extracting full code
                extracted = extract_code(raw_diff)
                if extracted and len(extracted) > _MIN_BASE_LEN and "class " in extracted:
                    _logger.info("LLM output has no SEARCH/REPLACE format but a complete code block was extracted; skipping the diff pipeline")
                    name, innovation, declared_ids = _parse_header(extracted)
                    path = os.path.join(config.CANDIDATES_DIR, f"candidate_gen{gen:03d}_{name}.py")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(extracted)
                    return {"path": path, "code": extracted, "name": name,
                            "innovation": innovation, "raw": raw_diff,
                            "mode": "base",
                            "fallback_reason": "llm_output_full_code_instead_of_diff",
                            "knowledge_ids": declared_ids or list(knowledge_ids or [])}
                else:
                    _logger.warning(f"LLM output not in diff format and no complete code extracted (length={len(raw_diff)}); falling back to BaseCoder")
            else:
                _logger.warning("LLM returned an empty response; falling back to BaseCoder")

            # Empty response or nothing extractable -> go straight to BaseCoder, skip diff retries
            result = self.base_coder.generate(
                best_algorithm=best_algorithm, reflection_text=reflection_text,
                knowledge_text=knowledge_text, forbidden_patterns=forbidden_patterns,
                gen=gen, knowledge_ids=knowledge_ids,
            )
            if result is None:
                return None
            result["mode"] = "base"
            result["fallback_reason"] = "llm_empty_or_non_diff_response"
            return result

        # regenerate_fn closure: re-render the prompt with current_code
        # (partially applied) on retries
        def regenerate_fn(current_code: str, retry_note: str) -> str:
            new_user = self.problem.render_prompt(
                gen_tmpl,
                best_algorithm=current_code,  # key: current_code, not best_algorithm
                reflection=reflection_text,
                knowledge=knowledge_text,
                forbidden_patterns=forbidden_patterns,
                knowledge_ids=_format_knowledge_ids(knowledge_ids),
            )
            new_user += "\n\n" + build_diff_format_suffix()
            if retry_note:
                new_user = retry_note + "\n\n" + new_user
            msgs = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": new_user},
            ]
            return self.llm.chat(msgs, role="generation")

        # Apply the diff patches (with retries)
        patched, total_applied, retry_note = apply_diff_with_retry(
            raw_diff, best_algorithm,
            max_retries=self.max_retries,
            regenerate_fn=regenerate_fn,
        )

        # Fallback decision: total failure
        if patched is None or total_applied == 0:
            import logging
            logger = logging.getLogger("kares")

            # Preferred strategy: try to extract full code from the raw LLM output
            # (the LLM may have produced a full algorithm without SEARCH/REPLACE wrapping)
            from ._utils import extract_code
            extracted = extract_code(raw_diff)
            if extracted and len(extracted) > _MIN_BASE_LEN and "class " in extracted:
                logger.info("Diff format failed, but a complete code block was extracted from the raw LLM output")
                name, innovation, declared_ids = _parse_header(extracted)
                path = os.path.join(config.CANDIDATES_DIR, f"candidate_gen{gen:03d}_{name}.py")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(extracted)
                return {"path": path, "code": extracted, "name": name,
                        "innovation": innovation, "raw": raw_diff,
                        "mode": "base",
                        "fallback_reason": "diff_failed_but_extracted_full_code",
                        "knowledge_ids": declared_ids or list(knowledge_ids or [])}

            # Last resort: re-invoke BaseCoder (costs one extra API call)
            logger.info("Diff failed and no code could be extracted from the raw output; falling back to BaseCoder")
            result = self.base_coder.generate(
                best_algorithm=best_algorithm, reflection_text=reflection_text,
                knowledge_text=knowledge_text, forbidden_patterns=forbidden_patterns,
                gen=gen, knowledge_ids=knowledge_ids,
            )
            if result is None:
                return None
            result["mode"] = "base"
            result["fallback_reason"] = f"diff_apply_failed: {retry_note}"
            return result

        # Success (partial success counts): parse header and write to disk
        # The header comment in patched should have been updated via SEARCH/REPLACE
        name, innovation, declared_ids = _parse_header(patched)
        path = os.path.join(config.CANDIDATES_DIR, f"candidate_gen{gen:03d}_{name}.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(patched)
        return {"path": path, "code": patched, "name": name,
                "innovation": innovation, "raw": raw_diff,
                "mode": "diff",
                "fallback_reason": retry_note or None,
                "knowledge_ids": declared_ids or list(knowledge_ids or [])}

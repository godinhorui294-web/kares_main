"""KARES code generators: diff (primary) + base (full-code fallback).

Mode is selected via config.CODE_GEN_MODE = "diff" (default) or "base":
- diff_coder: the LLM emits SEARCH/REPLACE patches applied to the previous
  generation's best algorithm
- base_coder: single-shot full-code generation (fallback)

Factory: get_coder(mode) returns the corresponding Coder class.
"""
from ._utils import extract_code, _parse_header
from .patcher import SearchReplacePatcher
from .apply import apply_diff_with_retry
from .diff_prompts import DIFF_SYS_FORMAT, build_base_diff_instructions, build_diff_format_suffix
from .base_coder import BaseCoder
from .diff_coder import DiffCoder


def get_coder(mode: str):
    """Factory: mode="diff" -> DiffCoder, "base" -> BaseCoder."""
    if mode == "diff":
        return DiffCoder
    if mode == "base":
        return BaseCoder
    raise ValueError(f"Unknown coder mode: {mode} (expected 'diff' or 'base')")


__all__ = [
    "extract_code",
    "_parse_header",
    "SearchReplacePatcher",
    "apply_diff_with_retry",
    "DIFF_SYS_FORMAT",
    "build_base_diff_instructions",
    "build_diff_format_suffix",
    "BaseCoder",
    "DiffCoder",
    "get_coder",
]

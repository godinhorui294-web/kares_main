# kares_workflow/coders

Code generator subpackage of KARES. Provides the diff (primary, incremental)
and base (full-code fallback) generators, selected via `config.CODE_GEN_MODE`,
with `get_coder(mode)` as the factory entry point.

## Module index

| Module | Responsibility |
|------|------|
| [__init__.py](file:///c:/kares_pipeline/kares_workflow/coders/__init__.py) | Package entry; `get_coder(mode)` factory; re-exports public helpers |
| [_utils.py](file:///c:/kares_pipeline/kares_workflow/coders/_utils.py) | `extract_code` (pulls ` ```python ` blocks from LLM output), `_parse_header` (parses the algorithm name / innovation header comment) |
| [base_coder.py](file:///c:/kares_pipeline/kares_workflow/coders/base_coder.py) | **BaseCoder**: single-shot full-code generation; one LLM call produces the plan plus the complete code block; fallback for diff failures |
| [diff_coder.py](file:///c:/kares_pipeline/kares_workflow/coders/diff_coder.py) | **DiffCoder**: the LLM emits SEARCH/REPLACE patches applied to the previous best; falls back to BaseCoder on empty base / application failure |
| [diff_prompts.py](file:///c:/kares_pipeline/kares_workflow/coders/diff_prompts.py) | SEARCH/REPLACE format constants (`DIFF_SYS_FORMAT`, `build_diff_format_suffix`, `build_base_diff_instructions`) |
| [patcher.py](file:///c:/kares_pipeline/kares_workflow/coders/patcher.py) | **SearchReplacePatcher**: pure utility class applying SEARCH/REPLACE patches to source code; zero business dependencies (only `re`/`difflib`/`typing`) |
| [apply.py](file:///c:/kares_pipeline/kares_workflow/coders/apply.py) | `apply_diff_with_retry`: patch application + failure diagnostics + retry pipeline; reused by DiffCoder and MechanicalBarrier |

## Mode switching

```python
# kares_workflow/config.py
CODE_GEN_MODE = "diff"   # default; SEARCH/REPLACE incremental
# CODE_GEN_MODE = "base" # single-shot full-code generation (fallback)
```

## Key design points of diff mode

1. Empty / very short `best_algorithm` -> immediate fallback to `BaseCoder` (cannot patch empty code).
2. The LLM output is SEARCH/REPLACE text rather than a ` ```python ` block, so it does **not** go through `extract_code`; it is fed directly to `apply_diff_with_retry`.
3. The `regenerate_fn` closure re-renders the prompt with the **partially applied current_code**; otherwise the LLM would see stale code and its SEARCH blocks would never match.
4. The prompt explicitly asks for the header comment (algorithm name / innovation) to be updated via SEARCH/REPLACE, and `_parse_header` runs again after patching.
5. `patched is None or total_applied == 0` -> total failure, fall back to base; `total_applied > 0` -> success (partial success is accepted; retry_note records it without triggering a fallback).
6. Diff format instructions are injected dynamically by `build_diff_format_suffix()`; templates carry only business logic.

## Callers

- [orchestrator.py](file:///c:/kares_pipeline/kares_workflow/orchestrator.py) instantiates coders via `get_coder(config.CODE_GEN_MODE)(...)`.
- [mechanical_barrier.py](file:///c:/kares_pipeline/kares_workflow/mechanical_barrier.py) reuses `apply_diff_with_retry` and `extract_code` during the mechanical barrier repair stage.

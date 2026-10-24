# Prompts Directory

This directory holds the **problem-agnostic** prompt templates used by the KARES workflow. All templates use the `{{placeholder}}` syntax and are substituted at runtime by `render_prompt(template, **kwargs)` in `kares_workflow/problem_loader.py`. Switching to a different problem or constraint set requires **no modification of any file in this directory** — just provide `problem_brief.md` and `constraints.md` under `problems/<problem_name>/`.

## Directory Structure

```
prompts/
├── system/
│   └── system_prompt.md              # System prompt + rule-layer meta-rules (prepended as the system message of every LLM call)
├── reflection/
│   ├── horizontal_reflection.md      # Horizontal Reflection: structural comparison within a generation (incl. innovation assessment)
│   └── vertical_reflection.md        # Vertical Reflection: cross-generation best-trajectory tracking (incl. innovation direction prediction)
├── generation/
│   ├── algorithm_generation.md       # Candidate algorithm generation (full code; core)
│   └── algorithm_generation_diff.md  # Candidate algorithm generation (SEARCH/REPLACE incremental improvement)
├── barrier/
│   ├── evaluation.md                 # Evaluation Agent: syntax/constraint/runtime checks
│   ├── improvement.md                # Improvement Agent: repair code per report (full code)
│   ├── improvement_diff.md           # Improvement Agent: SEARCH/REPLACE repair
│   └── verification.md               # Verification Agent: AST structural comparison + sandbox run
└── enrichment/
    └── knowledge_enrichment.md       # Knowledge Enrichment Agent: distill new knowledge from experiment results
```

## Placeholder Conventions

| Placeholder | Meaning | Source |
|-------------|---------|--------|
| `{{problem_brief}}` | Problem brief text | `problems/<problem>/problem_brief.md` |
| `{{constraints}}` | Constraint list text | `problems/<problem>/constraints.md` |
| `{{interface_contract}}` | Algorithm interface contract | `kares_workflow/config.py` constants |
| `{{best_algorithm}}` | Current best algorithm code | algorithm pool |
| `{{pool_summary}}` | Structural summary of same-generation algorithms | algorithm pool |
| `{{history_trajectory}}` | Cross-generation best trajectory | algorithm pool history |
| `{{reflection}}` | Dual-track reflection output (Rh+Rv) | dual_reflection |
| `{{knowledge}}` | Retrieved knowledge fragments | knowledge_base |
| `{{eval_report}}` | Evaluation report | mechanical_barrier |
| `{{candidate_code}}` | Candidate code to repair | mechanical_barrier |
| `{{forbidden_patterns}}` | Forbidden patterns (failure cases) | knowledge sedimentation |

## Switching to a New Problem

1. Create `problems/<new_problem>/` and add `problem_definition.json`, `problem_brief.md`, `constraints.md`, and the instances;
2. Run `python run_kares.py --problem <new_problem>`;
3. The templates in this directory are automatically filled with the new problem's content — no changes required.

See [doc/workflow_design.md](../doc/workflow_design.md) for details.

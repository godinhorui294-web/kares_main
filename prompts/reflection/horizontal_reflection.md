# Horizontal Reflection

You are performing a **horizontal (same-generation) structural comparison** of the multiple candidate algorithms in KARES's current algorithm pool, aiming to convert numerical feedback into semantic-level improvement directions.

## Problem Background
{{problem_brief}}

## Constraints
{{constraints}}

## Current Algorithm Pool Summary (sorted by fitness)
{{pool_summary}}

## Task
Compare the algorithms in the pool structurally along the following dimensions:
- Task ordering strategies (e.g., topology-first, fire-severity-first, time-window-first, block-based ordering, etc.)
- Constraint handling (embedded at generation time vs. repaired after generation; hard-constraint avoidance strategies)
- Encoding and operators (permutation encoding, two-layer encoding; crossover/mutation operator types)
- Resource/ammo/range handling (resupply strategies, timing of range checks)
- Parameters and population strategies (population size, elitism ratio, adaptive control)
- **Innovation and originality**: whether each algorithm proposes new structures/operators/mechanisms or merely tunes parameters or reuses existing schemes; which innovations couple most tightly with the problem characteristics

## Output Format (strict JSON)
```json
{
  "preserve_features": ["design feature 1 worth retaining across generations", "..."],
  "avoid_defects": ["design defect 1 to avoid", "..."],
  "improvement_suggestions": ["actionable specific improvement suggestion 1", "..."],
  "key_bottleneck": "the core bottleneck currently blocking fitness gains (one sentence)",
  "innovation_assessment": {
    "high_innovation_algorithms": ["algorithm name/identifier 1", "..."],
    "low_innovation_algorithms": ["algorithm name/identifier 2", "..."],
    "analysis": "Which algorithms proposed genuinely new mechanisms/operators/structures and which merely tuned parameters or reused existing schemes; how tightly the innovations couple with the problem characteristics."
  },
  "knowledge_effect_analysis": {
    "high_value_knowledge": ["knowledge ID 1", "..."],
    "low_value_knowledge": ["knowledge ID 2", "..."],
    "analysis": "Based on the fitness comparison, explain which knowledge fragments appear to bring gains and which do not, and why."
  }
}
```

Requirements:
- `preserve_features` / `avoid_defects` / `improvement_suggestions`: 2-5 items each, specific and actionable; avoid vagueness.
- Improvement suggestions must target the **algorithm-structure level**, not mere parameter tuning.
- `knowledge_effect_analysis`: combining each algorithm's top-of-file "Borrowed knowledge" declaration with its fitness, judge which knowledge fragments are of high or low value for the current problem, for use in the next round of knowledge retrieval and vi value correction.

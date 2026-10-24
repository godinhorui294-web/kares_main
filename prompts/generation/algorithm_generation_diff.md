# Candidate Algorithm Generation (Diff Mode — SEARCH/REPLACE Incremental Improvement)

Based on the problem definition, the current best algorithm, the dual-track reflection output, and retrieved external knowledge, you will make incremental improvements to the current best algorithm.
You **must not output complete code**; output only SEARCH/REPLACE patch blocks.

## Problem Brief
{{problem_brief}}

## Constraint List
{{constraints}}

## Algorithm Interface Contract (must be strictly observed)
{{interface_contract}}

## Current Algorithm to Modify (patches will be applied on this base)
```python
{{best_algorithm}}
```

## Improvement Plan (must be implemented via SEARCH/REPLACE; do not deviate)
{{reflection}}

## Retrieved External Knowledge (may be borrowed; sources must be attributed)
{{knowledge}}

## Knowledge Node IDs Hit by This Retrieval (any borrowed subset must be declared in the top-of-file comment)
{{knowledge_ids}}

## Forbidden Patterns (known failure structures; must not be reproduced)
{{forbidden_patterns}}

## Generation Requirements

1. **Output SEARCH/REPLACE blocks only** — no complete code and no ```python code blocks. Each SEARCH must be copied **verbatim** from the "Current Algorithm to Modify" above (with exact indentation).
2. Strictly conform to the algorithm interface contract above.
3. **Use one SEARCH/REPLACE block to update the top-of-file comment** — "Algorithm name", "Innovation", and "Borrowed knowledge" — to this generation's new values; otherwise the new candidate cannot be recognized. The new algorithm name should directly reflect this generation's core innovation, and the innovation comment must specifically state the new mechanism/operator/structure added (1-2 sentences). Borrowed knowledge must list the subset of actually borrowed node ids in the following format:
   `# Borrowed knowledge: [K_p_KB-001, K_p_KB-007]`
   If no knowledge node is borrowed, write `# Borrowed knowledge: []`. This declaration is used to write back knowledge applicability (vi); fill it in truthfully.
4. **Algorithm innovation requirement (core)**:
   - Each generation's candidate algorithm must propose a clear innovation in at least one dimension: a new heuristic construction/decoding strategy, a new encoding/chromosome structure, a new crossover/mutation/neighborhood operator, a new adaptive/learning mechanism, a new multi-objective trade-off scheme, a new constraint-handling mechanism, or a novel combination of multiple classical strategies.
   - Mere parameter tuning, constant adjustment, renaming of existing operators without substantive change, or minor patching on top of the previous generation is forbidden.
   - The innovation must be directly reflected in the top-of-file comment and the algorithm name, with a theoretical or problem-intuition justification (1-2 sentences), e.g.: why the structure suits the current problem, which bottleneck it is expected to resolve, and how it differs from classical methods.
   - If external knowledge is borrowed, it must be combined with the problem characteristics to form a novel variant tailored to the current problem, not mechanically copied.
5. Make structural improvements targeting the reflection output's improvement suggestions — do not merely tune parameters; if external knowledge is borrowed, attribute the source in the top-of-file comment.
6. Make minimal, targeted changes; preserve all interfaces, variable names, and compatibility constraints; do not break the existing correct algorithmic structure.
7. Use only the Python standard library and `numpy` (optional); do not depend on external packages that are not provided; no undefined variables or unimported modules.
8. Multiple independent modifications may be proposed; arrange the SEARCH/REPLACE blocks sequentially, with no other text between blocks.

Output the SEARCH/REPLACE blocks directly, without extra explanation.

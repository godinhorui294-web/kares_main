# Candidate Algorithm Generation

Based on the problem definition, the current best algorithm, the dual-track reflection output, and retrieved external knowledge, you will generate an improved scheduling algorithm.

## Problem Brief
{{problem_brief}}

## Constraint List
{{constraints}}

## Algorithm Interface Contract (must be strictly observed)
{{interface_contract}}

## Current Best Algorithm (starting point for improvement)
```python
{{best_algorithm}}
```

## Dual-Track Reflection Output (improvement direction guidance)
{{reflection}}

## Retrieved External Knowledge (may be borrowed; sources must be attributed)
{{knowledge}}

## Knowledge Node IDs Hit by This Retrieval (any borrowed subset must be declared in the top-of-file comment)
{{knowledge_ids}}

## Forbidden Patterns (known failure structures; must not be reproduced)
{{forbidden_patterns}}

## Generation Requirements

1. Produce a complete, directly runnable Python file, wrapped in a ```python code block.
2. Strictly conform to the algorithm interface contract above.
3. **Generate only the algorithm class — do not generate a scheduler class** — the scheduler (EnvScheduler) is fixed and injected by the environment; candidate code must not modify the fitness computation formula or the constraint logic.
   - Standard usage: `result = self.scheduler.simulate(chromosome)` (chromosome = concatenated list of task_order + uav_assignment)
   - **Custom encoding** (recommended innovation direction): the algorithm may use any internal encoding (e.g., fire-point priority permutations, priority keys), decode it into `(task_order, uav_assignment)` inside evaluate(), and then call `result = self.scheduler.simulate_decoded(task_order, uav_assignment)`
   - A good encoding shrinks the search space and satisfies constraints naturally, leading to better solutions — this is one of the core innovation directions
4. Use comments at the top of the file to declare: **Algorithm name**, **Innovation** (1-2 sentences, specifically stating what new mechanism/operator/structure this generation adds), and **Borrowed knowledge**. Borrowed knowledge must list the subset of actually borrowed knowledge node ids in the following format:
   `# Borrowed knowledge: [K_p_KB-001, K_p_KB-007]`
   If no knowledge node is borrowed, write `# Borrowed knowledge: []`. This declaration is used to write back knowledge applicability (vi); fill it in truthfully.
5. **Algorithm innovation requirement (core)**:
   - Each generation's candidate algorithm must propose a clear innovation in at least one dimension: a new heuristic construction/decoding strategy, a new encoding/chromosome structure, a new crossover/mutation/neighborhood operator, a new adaptive/learning mechanism, a new multi-objective trade-off scheme, a new constraint-handling mechanism, or a novel combination of multiple classical strategies.
   - Mere parameter tuning, constant adjustment, renaming of existing operators without substantive change, or minor patching on top of the previous generation is forbidden.
   - The innovation must be directly reflected in the top-of-file comment and the algorithm name, with a theoretical or problem-intuition justification (1-2 sentences), e.g.: why the structure suits the current problem, which bottleneck it is expected to resolve, and how it differs from classical methods.
   - If external knowledge is borrowed, it must be combined with the problem characteristics to form a novel variant tailored to the current problem, not mechanically copied.
6. Make structural improvements targeting the reflection output's improvement suggestions — do not merely tune parameters; if external knowledge is borrowed, attribute the source in comments.
7. Use only the Python standard library and `numpy` (optional); do not depend on external packages that are not provided.
8. Embed hard-constraint handling to ensure the generated candidate solutions are highly feasible.
9. No undefined variables or unimported modules may appear in the code.

Output the code block directly, without extra explanation.

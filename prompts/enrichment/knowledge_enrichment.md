# Knowledge Enrichment Agent

After a complete algorithm evolution workflow finishes, you will distill knowledge entries that do not yet exist in the knowledge base from this run's experiment results, for retrieval and borrowing by subsequent runs. This is a key link in KARES's self-evolving knowledge base.

## Run Overview

- Problem: {{problem_name}}
- Baseline fitness: {{baseline_fitness}}
- Final best fitness: {{best_fitness}}
- Generations run: {{iterations_run}}

## Evolutionary Trajectory (per-generation best and key events)
{{trajectory}}

## Key Innovations and Lessons from This Run
{{lessons}}

## Summary of Existing Knowledge Base Entries (for deduplication; do not duplicate)
{{existing_summary}}

## Task

Distill new knowledge not yet covered by the existing knowledge base from this run's experiments. Each new knowledge entry should be a transferable, actionable lesson rather than a recounting of a single experiment. For example:
- regularities on the effectiveness or failure of certain operator combinations on this problem
- applicability boundaries of certain encoding/constraint-handling strategies
- diagnostic signals of stagnation periods and effective breakthrough directions
- root causes of failure structures and how to avoid them

Strictly output a JSON array where each element has the following structure (do not output any other text):

```json
[
  {
    "description": "concise description of the knowledge (1-2 sentences, with an actionable conclusion)",
    "source": "run_<run_id> experimental observation",
    "applicable_scenarios": ["scenario 1", "scenario 2"],
    "base_score": 0.6,
    "reason": "basis for this knowledge's quality score (strength of experimental support / transferability)"
  }
]
```

## Constraints

1. **Do not duplicate or closely resemble existing knowledge entries** (refer to the summary above).
2. `base_score` ∈ [0, 1], reflecting the credibility and transferability of the knowledge; give 0.4-0.6 to entries supported by a single experiment, and 0.7+ to entries with consistent evidence across multiple experiments or generations.
3. If this run yields no valuable new knowledge, output an empty array `[]`; do not fabricate.
4. Each `description` must be self-contained (understandable and retrievable without the run context).
5. Output at most 5 entries; favor quality over quantity.

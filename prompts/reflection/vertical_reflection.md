# Vertical Reflection

You are performing a vertical analysis of KARES's cross-generation evolutionary trajectory, aiming to identify the structural features persistently retained across generations and the causal patterns behind improvements.

## Problem Background
{{problem_brief}}

## Cross-Generation Best Trajectory (most recent {{window}} generations)
{{history_trajectory}}

## Task
Analyze the improvement relationships between the current best and the historical bests of recent generations:

1. **Persistent features**: Which structural features keep appearing in the best solutions across multiple generations (indicating their effectiveness)?
2. **Generational leap causes**: For each significant fitness improvement, what structural change was introduced? Do these changes constitute genuine algorithmic innovation (new mechanisms/operators/structures), or merely parameter tuning?
3. **Stagnation causes**: If there has been no recent improvement, what are the likely causes (insufficient exploration / premature convergence / constraint bottleneck / exhausted innovation space)?
4. **Next breakthrough direction**: Based on the evolutionary trend, predict the algorithmic innovation direction most likely to break through the current bottleneck. The direction must be a **new structure/operator/mechanism** not adequately explored in previous generations, not parameter fine-tuning of existing designs.

## Output Format (strict JSON)
```json
{
  "persistent_features": ["structural feature 1 persistently retained across generations", "..."],
  "leap_causes": [{"from_gen": 0, "to_gen": 0, "change": "structural change description", "is_innovation": true, "delta_fitness": 0.0}],
  "stagnation_reason": "cause analysis if stagnant; otherwise null",
  "next_breakthrough_direction": "the structural innovation direction most likely to break the bottleneck (be specific)",
  "innovation_retrospective": "Review which improvements across the cross-generation trajectory were genuine algorithmic innovations and which were mere parameter tuning or local patching; which untried innovation dimensions should be prioritized in the future."
}
```

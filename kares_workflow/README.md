# kares_workflow

Core package of the KARES **autonomous algorithm innovation workflow**. It
implements the accumulative closed loop "reflection → retrieval → generation →
verification (mechanical barrier) → diversity screening → evaluation →
sedimentation", orchestrated by `KARESOrchestrator` and invoked by the
top-level `run_kares.py`.

Entry point: `from kares_workflow import KARESOrchestrator` (see
[__init__.py](__init__.py)).

## Module index

| Module | Responsibility |
|--------|----------------|
| [orchestrator.py](orchestrator.py) | **Main closed-loop orchestration**: seed → reflection → retrieval → generation → barrier → diversity → evaluation → sedimentation, with per-run directory isolation (`outputs/run_<ts>/`) |
| [config.py](config.py) | Paths, iteration parameters, model roles, interface contract; reuses API keys / providers from the root `config.py` |
| [problem_loader.py](problem_loader.py) | Loads the problem definition / brief / constraints / instance list; renders `{{ var }}` placeholders; per-problem overrides of `instance_pattern` / `interface_contract` |
| [knowledge_base.py](knowledge_base.py) | Knowledge base loading / retrieval / sedimentation; delegates to `KnowledgeGraph` internally with a stable public interface; falls back to the legacy TF-IDF path when the graph is corrupted |
| [knowledge_graph.py](knowledge_graph.py) | Knowledge graph: nodes (papers / workflow knowledge) + edges (knowledge↔problem, carrying `vi` values); EWMA (α=0.3) updates; accumulates across runs on disk |
| [knowledge_graph_builder.py](knowledge_graph_builder.py) | One-shot migration: builds `knowledge_graph.json` from `knowledge_base_unified.json`; re-runnable (incremental merge) |
| [knowledge_enrichment_agent.py](knowledge_enrichment_agent.py) | Distills **new knowledge entries** from the evolutionary trajectory at the end of a run into the graph (`K_w_<run_id>_<hash>`), with TF-IDF cosine dedup |
| [algorithm_pool.py](algorithm_pool.py) | Candidate algorithm pool + cross-generation best-fitness history; fitness-descending, capacity-pruned |
| [dual_reflection.py](dual_reflection.py) | **Dual-track reflection**: horizontal (within-generation comparison) + vertical (cross-generation trajectory) → synthesized retrieval query + improvement-directions text injected into prompts |
| [llm_client.py](llm_client.py) | Provider-agnostic LLM client (OpenAI-compatible protocol); supports deepseek / dashscope(qwen) / moonshot(kimi) |
| [mechanical_barrier.py](mechanical_barrier.py) | **Mechanical barrier**: AST syntax pre-check → interface contract validation → sandbox pre-run → LLM evaluate/improve/verify repair loop |
| [evaluator.py](evaluator.py) | Runs candidate algorithms in isolated subprocesses with per-instance timeouts; locates `SCHEDULER_CLASS` / `ALGORITHM_CLASS` via AST |
| [diversity_filter.py](diversity_filter.py) | Two-level hash fingerprint dedup: structural (class/function skeleton) + logical (method-body AST sequence); a duplicate requires both to match |
| [coders/](coders/) | **Code generator subpackage**: diff (primary SEARCH/REPLACE incremental) + base (full-rewrite fallback) modes; see the subdirectory README |

## Closed-loop data flow

```
seed (baseline) ──► DualReflection ──► KnowledgeBase.retrieve ──► Coder.generate
                                                                          │
   ◄── KnowledgeEnrichmentAgent ◄── AlgorithmPool ◄── Evaluator ◄── MechanicalBarrier
                                                                         │
                                                                  DiversityFilter
```

## Per-run artifact isolation

Every `KARESOrchestrator.run()` creates a dedicated subdirectory under
`outputs/run_<timestamp>/`:

- `candidates/`: LLM-generated candidate algorithms (`.py`) per generation
- `checkpoints/`: per-generation snapshots of the `AlgorithmPool` state
- `logs/run.log`: the run log
- `enrichment/new_knowledge.json`: knowledge distilled during this run
- `final_report.json` / `sedimented_knowledge.json`: final report and sediment

Cross-run **accumulating** artifacts (the knowledge graph, the base_score
cache) live under `knowledge/`, outside the per-run directories, so run_id
isolation never wipes them.

## Swapping in a new problem

1. Provide `problem_definition.json` / `problem_brief.md` / `constraints.md`
   under `problems/<new_problem>/`.
2. Put instances under `instances/` (or point `instance_pattern` elsewhere).
3. Provide the seed algorithm `algorithms/baseline/<new_problem>_soga.py`.
4. Run `KARESOrchestrator(problem_name="<new_problem>")`.

See [doc/workflow_design.md](../doc/workflow_design.md) for details.

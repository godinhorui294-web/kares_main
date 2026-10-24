# KARES Automatic Algorithm Innovation Workflow — Architecture Design

> This document describes the closed-loop architecture of `kares_workflow/`, the responsibilities of each module, the data flows, and how to **swap in new problems and constraints**. For background see [proposal.md](./proposal.md).

## 1. Closed-Loop Overview

KARES implements the accumulative closed loop of **"reflect — retrieve — generate — verify — sediment"**, orchestrated by `kares_workflow/orchestrator.py`:

```
┌──────────────────────────────────────────────────────────────────┐
│                     KARESOrchestrator.run()                      │
│                                                                  │
│  Init: ProblemLoader → KnowledgeBase → AlgorithmPool(seed=baseline)│
│                                                                  │
│  for t in 1..N:                                                  │
│   ① Dual-track reflection  DualReflection(pool, history)         │
│      ├─ Horizontal reflection Rh: within-generation algorithm    │
│      │    structure comparison → keep / avoid / improve advice   │
│      └─ Vertical reflection Rv: cross-generation best-trajectory │
│           tracking → persistently retained structural features   │
│      ⇒ synthesize retrieval query q + improvement direction      │
│        (explicit constraints)                                    │
│   ② Knowledge retrieval  KnowledgeBase.retrieve(q, top_k) → K    │
│   ③ Candidate generation  CodeGenerator.generate(problem, best, Rh, Rv, K) │
│      ⇒ candidate code c (written to outputs/candidates/)         │
│   ④ Mechanical barrier  MechanicalBarrier(c, problem)            │
│      └─ EvaluationAgent → ImprovementAgent → VerificationAgent   │
│         (at most 3 rounds)                                       │
│      ⇒ feasible code c' (or failure + prohibitive constraints)   │
│   ⑤ Diversity screening  DiversityFilter(c', pool) → admit / dedup│
│   ⑥ Evaluation  Evaluator(c', instances) → fitness f             │
│   ⑦ Pool update  AlgorithmPool.update(c', f)                     │
│   ⑧ Knowledge sedimentation  KnowledgeBase.sediment(Rh, Rv, repair_logs) │
│      ⇒ experience / failure cases written back to                │
│         outputs/sedimented_knowledge.json                        │
│                                                                  │
│  Terminal state: output best algorithm a* + evolution report      │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Module Responsibilities (`kares_workflow/`)

| File | Responsibility | Key interface |
|------|----------------|---------------|
| `config.py` | Paths, iteration parameters, model selection; reuses API key/provider from the root `config.py` | Constants + `Paths` |
| `llm_client.py` | Provider-agnostic LLM client (deepseek/dashscope/moonshot, OpenAI-compatible) | `LLMClient.chat(messages, cfg)` |
| `problem_loader.py` | Loads problem definition + instances + prompt fragments; renders placeholders | `ProblemLoader(problem_name)` |
| `knowledge_base.py` | Knowledge base loading/retrieval/sedimentation (temporarily bridged to the unified schema) | `retrieve(query, top_k)` / `sediment(entry)` |
| `evaluator.py` | Runs algorithms on instances, collects fitness (subprocess isolation + timeout) | `evaluate_algorithm(code_path, instances)` |
| `dual_reflection.py` | Horizontal + vertical reflection → improvement direction + retrieval query | `reflect(pool, history)` |
| `code_generator.py` | Assembles prompts, calls the LLM, extracts code blocks | `generate(...)` |
| `mechanical_barrier.py` | Evaluate → improve → verify closed loop; converts failure cases into prohibitive constraints | `barrier(code_path, problem)` |
| `diversity_filter.py` | Structure-level + logic-level AST hash deduplication | `fingerprint(code)` / `is_duplicate` |
| `algorithm_pool.py` | Algorithm pool and historical trajectory management | `update/best/prune` |
| `orchestrator.py` | Main closed-loop orchestration | `KARESOrchestrator.run()` |

## 3. Data Flows and Interface Contracts

### 3.1 Algorithm Interface Contract (generated algorithms must comply)

Taking [`algorithms/baseline/uav_firefighting_soga.py`](../algorithms/baseline/uav_firefighting_soga.py) as the template, generated algorithm code must:

- Expose a **scheduler class** (e.g., `SingleObjectiveScheduler`): `__init__(self, data_file, random_seed=None)` loads the instance and implements `simulate(chromosome) -> dict` (containing `fitness`).
- Expose an **algorithm class** (e.g., `SimpleGA`): `__init__(self, scheduler, **kwargs)` implements `run(verbose=False) -> dict`, returning at least:
  ```
  { "best_fitness": float, "best_result": dict, "best_individual": list,
    "evaluation_count": int, "generations_completed": int }
  ```
- `evaluator.py` locates the algorithm class via the module-level constant `ALGORITHM_CLASS` (by default it looks for classes ending in `GA`/`Algorithm`/`Optimizer`, or an explicit `SOLVER_CLASS` constant), instantiates it with `data_file`, and calls `run()`.

### 3.2 Problem Loading

`ProblemLoader(problem_name)` reads `problems/<problem_name>/`:
- `problem_definition.json` — structured problem definition (machine-readable)
- `problem_brief.md` — problem brief (injected into prompts)
- `constraints.md` — constraint list (injected into prompts)
- Instance files: matched via `config.INSTANCES_DIR` plus the instance name pattern (e.g., `firefighting_instance_*.json`)

### 3.3 Knowledge Base Retrieval

`knowledge_base.py` loads the `papers` list from `knowledge/knowledge_base_unified.json` in this isolated directory, flattening each `layer_2_knowledge_base` entry (`algorithm_name` + `core_innovations` + `algorithm_flow` + `encoding_and_operators` + `problem_domain`) into text; `retrieve(query, top_k)` ranks by TF-IDF cosine similarity (scikit-learn is used when available, with a pure-Python term-frequency fallback otherwise). **For later field restructuring, only this file needs to change.**

## 4. Swapping Problems and Constraints (Core Goal)

### 4.1 Adding a Problem

1. Create a subdirectory under `problems/`, e.g., `problems/my_problem/`:
   ```
   problems/my_problem/
   ├── problem_definition.json   # structured definition
   ├── problem_brief.md          # problem brief
   ├── constraints.md            # constraint list
   └── instances/                # instances (or point to the shared instances/ via config)
   ```
2. If instances live in the shared `instances/`, add a top-level `"instance_pattern": "my_inst_*.json"` field to `problem_definition.json`; `ProblemLoader` matches against it.
3. Run: `python run_kares.py --problem my_problem`
4. **No prompt template changes needed** — the templates under `prompts/` use placeholders such as `{{problem_brief}}` and `{{constraints}}`, automatically filled with the new problem's content.

### 4.2 Modifying Constraints

Edit `problems/<problem>/constraints.md` directly; the change takes effect on the next iteration. Constraint changes are injected via prompts into both generation and the barrier stages.

### 4.3 Switching LLM / Tuning Parameters

- LLM provider/model: edit `PRIMARY_MODEL` / `EVALUATION_MODEL` in this directory's `config.py`, or remap roles in `MODEL_ROLES` in `kares_workflow/config.py`.
- Iteration parameters: `max_iterations`, `barrier_max_rounds`, `pool_size`, `patience` in `kares_workflow/config.py`.

## 5. Output Structure (`outputs/`, created at runtime)

```
outputs/
├── candidates/          # candidate algorithm .py generated each generation
├── checkpoints/         # per-generation pool snapshots (JSON)
├── logs/                # run logs
└── sedimented_knowledge.json   # sedimented experience / failure-case knowledge
```

## 6. Dependencies

- Required: `openai` (LLM calls, OpenAI-compatible protocol)
- Optional: `numpy` (baseline acceleration), `scikit-learn` (TF-IDF retrieval acceleration); the system automatically degrades to pure-Python implementations when they are missing.
- LLM API keys come from this directory's `config.py` (`DASHSCOPE_API_KEY` / `DEEPSEEK_API_KEY` / `MOONSHOT_API_KEY`).

# KARES: A Knowledge-Driven Framework for Autonomous Algorithm Discovery in Scheduling

KARES is a framework that uses large language models to autonomously discover,
improve, and validate scheduling algorithms. It couples three mechanisms into a
single closed loop of **reflect — retrieve — generate — verify — sediment**:

- **Self-evolving knowledge base** — external literature and accumulated
  experimental experience are organized as a knowledge graph; retrieval is
  ranked jointly by similarity, problem-solving success, and a viability index
  (vi) updated online via EWMA.
- **Dual-track reflection** — horizontal reflection compares candidate
  structures within a generation, vertical reflection tracks cross-generation
  trajectories; together they convert numerical feedback into structural
  improvement guidance.
- **Mechanical barrier** — syntax, contract, and runtime checks with proactive
  LLM repair filter and fix candidate code before evaluation, so that wasted
  evaluations are minimized.

See [doc/proposal.md](doc/proposal.md) for the full framework description and
[doc/workflow_design.md](doc/workflow_design.md) for the architecture.

## Installation

```bash
pip install openai numpy   # scikit-learn optional (falls back to pure-Python TF-IDF)
```

Python 3.9+ is recommended.

## Configuration

KARES talks to LLM providers through the OpenAI-compatible API. Copy the
example configuration and fill in your keys, or export them as environment
variables:

```bash
cp config.example.py config.py    # then edit config.py
# or
export DEEPSEEK_API_KEY="sk-..."
export DASHSCOPE_API_KEY="sk-..."
```

Model roles (generation / reflection / barrier) are assigned in
[`config.py`](config.py) and [`kares_workflow/config.py`](kares_workflow/config.py).

## Quick Start

```bash
# UAV forest firefighting scheduling (default problem)
python run_kares.py --problem uav_firefighting --iterations 20

# Smoke run: first 3 instances, 2 generations
python run_kares.py --problem uav_firefighting --iterations 2 --instances 3

# CVRP benchmark sets (Christofides/Eilon, Golden, Christofides/Mingozzi/Toth)
python run_kares.py --problem cvrp_set_p --iterations 10
```

Run artifacts (candidates, checkpoints, logs, sedimented knowledge) are written
to `outputs/`.

## Project Structure

```
├── run_kares.py              # entry point
├── config.py                 # API keys / model roles (not committed)
├── kares_workflow/           # workflow implementation
│   ├── orchestrator.py       # main loop
│   ├── dual_reflection.py    # horizontal + vertical reflection
│   ├── knowledge_base.py     # retrieval / sedimentation
│   ├── knowledge_graph.py    # knowledge graph with vi values
│   ├── mechanical_barrier.py # evaluation → improvement → verification
│   ├── evaluator.py          # sandboxed evaluation harness
│   └── coders/               # full-code and SEARCH/REPLACE generators
├── prompts/                  # problem-agnostic prompt templates ({{placeholders}})
├── problems/                 # problem definitions (one directory per problem)
├── algorithms/baseline/      # baseline algorithms
├── knowledge/                # knowledge graph + unified knowledge base (data)
├── instances/                # test instances (133 files)
├── tools/                    # instance conversion / verification utilities
├── doc/                      # proposal and workflow design documents
└── outputs/                  # run artifacts (created at runtime)
```

## Adding a New Problem

1. Create `problems/<problem>/` with:
   - `problem_definition.json` — structured definition (optionally set
     `"instance_pattern"` to select instances, or `"instances_dir"` for a
     dedicated directory)
   - `problem_brief.md` — problem summary
   - `constraints.md` — constraint list
   - instances (in `instances/` or a custom `instances_dir`)
2. Place a baseline algorithm at `algorithms/baseline/<problem>_soga.py`
   (interface contract below).
3. Run `python run_kares.py --problem <problem>`. The prompt templates adapt
   automatically — no changes under `prompts/` are required.

Editing `problems/<problem>/constraints.md` takes effect from the next
generation onward.

## Algorithm Interface Contract

Generated algorithms must expose:

- **Scheduler interaction** — the environment injects a fixed scheduler; the
  algorithm calls `scheduler.simulate(chromosome)` or
  `scheduler.simulate_decoded(task_order, uav_assignment)` and must not modify
  fitness computation or constraint logic.
- **Algorithm class** (name containing `GA` / `Algorithm` / `Optimizer` / `PSO`
  / `SA` / `DE` / `Search`):
  - `__init__(self, scheduler, **kwargs)`
  - `run(self, verbose=False) -> dict` returning at least `best_fitness`,
    `best_result`, `best_individual`, `evaluation_count`, `generations_completed`

Reference implementation:
[`algorithms/baseline/uav_firefighting_soga.py`](algorithms/baseline/uav_firefighting_soga.py).

## Results

On 30 UAV forest firefighting instances, KARES improves upon the strongest
baseline (AlphaEvolve) by ~65.6% on average, and outperforms EoH and ReEvo by
~127.9% and ~126.8% respectively. Detailed tables are available in
[outputs/paper_table.md](outputs/paper_table.md); the underlying per-run data
is kept under `outputs/` for reproducibility.

## Citation

If you use KARES in your research, please cite:

```bibtex
@software{kares,
  title  = {KARES: A Knowledge-Driven Framework for Autonomous Algorithm Discovery in Scheduling},
  author = {KARES Authors},
  url    = {https://github.com/<your-org>/kares},
  year   = {2026}
}
```

## License

This project is released under the MIT License (see [LICENSE](LICENSE)).

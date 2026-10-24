# knowledge

KARES **knowledge base and knowledge graph** directory. Accumulates across runs and is **not** stored under `outputs/run_<ts>/`, so it survives per-run isolation.

## File Manifest

| File | Description |
|------|-------------|
| [knowledge_graph.json](knowledge_graph.json) | **Current knowledge graph**: nodes (papers `K_p_*` / workflow-distilled `K_w_*`) + edges (knowledge ↔ problem, carrying `vi` values); updated across runs with EWMA (α=0.3) |
| [knowledge_base_unified.json](knowledge_base_unified.json) | Legacy flat knowledge base (papers[] + layer_2_knowledge_base); currently the fallback source when `KnowledgeGraph` is corrupted, and the migration input for `knowledge_graph_builder` |
| `_base_score_cache.json` | LLM scoring cache for paper base_scores (keyed by paper_id hash), consumed once by `--llm-score` only |

## Subdirectories

- `_backups/`: timestamped snapshots of `knowledge_graph.json`, written automatically before each significant update (runtime artifact, not committed).

## Maintenance

- **Routine updates**: `kares_workflow/knowledge_graph.py` automatically updates `vi` values and writes them to disk (with backups) while the workflow runs.
- **Distilling new knowledge**: `knowledge_enrichment_agent.py` adds new experience to the graph at the end of each workflow round; node ids take the form `K_w_<run_id>_<hash>`.
- **One-off migration / rebuild**:
  ```bash
  python -m kares_workflow.knowledge_graph_builder                # heuristic base_score
  python -m kares_workflow.knowledge_graph_builder --llm-score   # LLM scoring (cached)
  python -m kares_workflow.knowledge_graph_builder --problem uav_firefighting --baseline 5034.28
  ```
  Migration is idempotent: it merges incrementally and never overwrites existing nodes' experimental data.
- **Fallback**: if the graph is corrupted, `KnowledgeBase` automatically falls back to the legacy TF-IDF path (loading `knowledge_base_unified.json`), keeping the workflow running.

See [kares_workflow/knowledge_graph.py](../kares_workflow/knowledge_graph.py) and Section 3.2 of [doc/proposal.md](../doc/proposal.md) for details.

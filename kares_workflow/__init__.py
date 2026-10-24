"""
kares_workflow — the KARES autonomous algorithm innovation workflow.

Closed loop: reflection → retrieval → generation → verification (mechanical
barrier) → diversity screening → evaluation → sedimentation.
Entry point: KARESOrchestrator (see orchestrator.py), invoked by the
top-level run_kares.py.
"""
from .config import (
    PROJECT_ROOT, PROBLEMS_DIR, PROMPTS_DIR, BASELINE_DIR, OUTPUTS_DIR,
    KB_PATH, INSTANCES_DIR, INTERFACE_CONTRACT, DEFAULT_PROBLEM,
    ensure_output_dirs, get_model_cfg, get_api_key,
)
from .orchestrator import KARESOrchestrator

__all__ = [
    "KARESOrchestrator", "PROJECT_ROOT", "PROBLEMS_DIR", "PROMPTS_DIR",
    "BASELINE_DIR", "OUTPUTS_DIR", "KB_PATH", "INSTANCES_DIR",
    "INTERFACE_CONTRACT", "DEFAULT_PROBLEM", "ensure_output_dirs",
    "get_model_cfg", "get_api_key",
]

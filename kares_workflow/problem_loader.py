"""
kares_workflow.problem_loader — load problem definitions, instance lists and
prompt templates; render placeholders.

Swapping in a new problem only requires problem_definition.json /
problem_brief.md / constraints.md under problems/<problem_name>/ plus,
optionally, a top-level "instance_pattern" field in problem_definition.json.
"""
import glob
import json
import os
import re
from typing import List

from . import config

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class ProblemLoader:
    """Loads the definition, brief, constraints and instance list of one problem."""

    def __init__(self, problem_name: str = config.DEFAULT_PROBLEM):
        self.problem_name = problem_name
        self.problem_dir = os.path.join(config.PROBLEMS_DIR, problem_name)
        if not os.path.isdir(self.problem_dir):
            raise FileNotFoundError(
                f"Problem directory not found: {self.problem_dir}. "
                f"Create a {problem_name}/ subdirectory under problems/."
            )

        self.definition = self._load_json(os.path.join(self.problem_dir, "problem_definition.json"))
        self.problem_brief = self._load_text(os.path.join(self.problem_dir, "problem_brief.md"))
        self.constraints = self._load_text(os.path.join(self.problem_dir, "constraints.md"))
        # The interface contract can be overridden per problem via
        # problems/<problem>/interface_contract.md; fall back to the config
        # default when the file is missing (same override mechanism as
        # instance_pattern/instances_dir).
        self.interface_contract = self._load_text(
            os.path.join(self.problem_dir, "interface_contract.md")
        ) or config.INTERFACE_CONTRACT
        self.instance_pattern = self.definition.get(
            "instance_pattern", config.DEFAULT_INSTANCE_PATTERN
        )
        # Use the instance directory from problem_definition.json if present,
        # otherwise the global instances/. Relative paths resolve against
        # PROJECT_ROOT so behavior does not depend on cwd.
        inst_dir = self.definition.get("instances_dir", config.INSTANCES_DIR)
        if inst_dir and not os.path.isabs(inst_dir):
            inst_dir = os.path.join(config.PROJECT_ROOT, inst_dir)
        self.instances_dir = inst_dir
        self.instance_files = self._discover_instances()
        # Baseline algorithm for this problem (convention:
        # algorithms/baseline/<problem>_soga.py, sharing the problem name)
        self.baseline_path = os.path.join(config.BASELINE_DIR, f"{problem_name}_soga.py")
        if not os.path.exists(self.baseline_path):
            # fallback: first .py found in the baseline directory
            for cand in glob.glob(os.path.join(config.BASELINE_DIR, "*.py")):
                self.baseline_path = cand
                break

        # Fixed environment scheduler (problems/<problem>/env_scheduler.py).
        # Candidate algorithms cannot modify the fitness formula; evaluation
        # always uses this scheduler.
        self.env_scheduler_path = os.path.join(self.problem_dir, "env_scheduler.py")
        if not os.path.exists(self.env_scheduler_path):
            self.env_scheduler_path = None  # fallback: the evaluator uses the candidate's own scheduler

    # ---- loading helpers ----
    @staticmethod
    def _load_json(path):
        # utf-8-sig tolerates BOM-prefixed files (common with Windows editors)
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)

    @staticmethod
    def _load_text(path):
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _discover_instances(self) -> List[str]:
        pattern = os.path.join(self.instances_dir, self.instance_pattern)
        files = sorted(glob.glob(pattern))
        return files

    def get_instances(self, limit: int = 0) -> List[str]:
        """Return instance files; limit>0 returns only the first limit (smoke runs)."""
        if limit and limit > 0:
            return self.instance_files[:limit]
        return self.instance_files

    # ---- prompt rendering ----
    def render_prompt(self, template: str, **kwargs) -> str:
        """
        Replace {{placeholders}} in the template with kwargs.
        Placeholders without a value become empty strings.
        """
        # problem texts and the interface contract are injected by default
        values = {
            "problem_brief": self.problem_brief,
            "constraints": self.constraints,
            "interface_contract": self.interface_contract,
        }
        values.update(kwargs)

        def _repl(m):
            key = m.group(1)
            val = values.get(key, "")
            return str(val) if val is not None else ""

        return _PLACEHOLDER_RE.sub(_repl, template)

    def load_prompt_template(self, *parts) -> str:
        """Read a template file under prompts/; parts are relative path segments."""
        path = os.path.join(config.PROMPTS_DIR, *parts)
        return self._load_text(path)

    def __repr__(self):
        return (f"ProblemLoader(name={self.problem_name!r}, "
                f"instances={len(self.instance_files)}, "
                f"baseline={os.path.basename(self.baseline_path)})")

    def get_direct_query(self) -> str:
        """Build the retrieval query for direct generation in generation 1 (no reflection yet)."""
        parts = []
        name = self.definition.get("problem_name", self.problem_name)
        desc = self.definition.get("description", "")
        parts.append(f"Problem: {name}")
        if desc:
            parts.append(f"Description: {desc}")

        scale = self.definition.get("1_problem_scale", {})
        enc = scale.get("chromosome_encoding", {})
        if enc.get("type"):
            parts.append(f"Encoding: {enc['type']}")
        tc = scale.get("task_constraints", {})
        for k, v in tc.items():
            parts.append(f"Constraint: {v}")

        obj = self.definition.get("4_objective_function", {})
        if obj.get("formula"):
            parts.append(f"Objective: {obj['formula']}")
        comps = obj.get("components", {})
        for k, v in comps.items():
            if isinstance(v, dict) and v.get("description"):
                parts.append(f"{k}: {v['description']}")

        # Fixed retrieval keywords: make sure scheduling / metaheuristic
        # knowledge gets hit even when the problem definition lacks such terms.
        parts.append("scheduling algorithm combinatorial optimization metaheuristic "
                     "genetic algorithm crossover mutation selection constraint handling encoding")
        return "\n".join(parts)

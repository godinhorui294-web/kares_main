#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
run_kares.py — entry point for the KARES autonomous algorithm innovation workflow.

Usage:
    python run_kares.py --problem uav_firefighting --iterations 20
    python run_kares.py --problem uav_firefighting --iterations 2 --instances 3   # smoke test
    python run_kares.py --problem tsp_test                                        # switch problem
"""
import argparse
import os
import sys

# Make sure the project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kares_workflow import KARESOrchestrator, config


def main():
    parser = argparse.ArgumentParser(description="KARES autonomous algorithm innovation workflow")
    parser.add_argument("--problem", default=config.DEFAULT_PROBLEM,
                        help=f"Problem name (directory under problems/, default {config.DEFAULT_PROBLEM})")
    parser.add_argument("--iterations", type=int, default=config.MAX_ITERATIONS,
                        help=f"Number of iterations (default {config.MAX_ITERATIONS})")
    parser.add_argument("--instances", type=int, default=config.DEFAULT_EVAL_INSTANCES,
                        help="Number of evaluation instances: 0 = all, >0 = first N only (for smoke tests, default 0)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default 42)")
    parser.add_argument("--skip-baseline-eval", action="store_true",
                        help="Skip baseline evaluation and use the baseline_fitness cached in the knowledge graph")
    parser.add_argument("--candidates-per-gen", type=int,
                        default=config.CANDIDATES_PER_GENERATION,
                        help=f"Candidates generated per generation (default {config.CANDIDATES_PER_GENERATION})")
    parser.add_argument("--knowledge-per-cand", type=int,
                        default=config.KNOWLEDGE_PER_CANDIDATE,
                        help=f"Knowledge snippets assigned per candidate (default {config.KNOWLEDGE_PER_CANDIDATE})")
    parser.add_argument("--knowledge-overlap", action="store_true",
                        help="Allow knowledge overlap between candidates (no overlap by default)")
    parser.add_argument("--early-stop-gen1-fails", type=int,
                        default=config.EARLY_STOP_GEN1_FAILS,
                        help=f"Stop when the number of non-runnable gen-1 candidates reaches this value (0 = disabled, default {config.EARLY_STOP_GEN1_FAILS})")
    args = parser.parse_args()

    # Runtime config overrides
    if args.candidates_per_gen != config.CANDIDATES_PER_GENERATION:
        config.CANDIDATES_PER_GENERATION = args.candidates_per_gen
    if args.knowledge_per_cand != config.KNOWLEDGE_PER_CANDIDATE:
        config.KNOWLEDGE_PER_CANDIDATE = args.knowledge_per_cand
    if args.knowledge_overlap:
        config.KNOWLEDGE_GROUP_NON_OVERLAP = False
    if args.early_stop_gen1_fails != config.EARLY_STOP_GEN1_FAILS:
        config.EARLY_STOP_GEN1_FAILS = args.early_stop_gen1_fails

    print(f"Problem: {args.problem} | Iterations: {args.iterations} | "
          f"Instances: {'all' if args.instances == 0 else 'first ' + str(args.instances)} | "
          f"Seed: {args.seed} | "
          f"Skip baseline eval: {'yes' if args.skip_baseline_eval else 'no'} | "
          f"Candidates per generation: {config.CANDIDATES_PER_GENERATION} | "
          f"Knowledge per candidate: {config.KNOWLEDGE_PER_CANDIDATE} | "
          f"Knowledge overlap: {'yes' if not config.KNOWLEDGE_GROUP_NON_OVERLAP else 'no'} | "
          f"Gen-1 early-stop threshold: {config.EARLY_STOP_GEN1_FAILS}")

    orchestrator = KARESOrchestrator(
        problem_name=args.problem,
        iterations=args.iterations,
        eval_instance_limit=args.instances,
        seed=args.seed,
        skip_baseline_eval=args.skip_baseline_eval,
    )
    report = orchestrator.run()
    print("\n=== Done ===")
    print(f"Best fitness: {report.get('best_fitness')}")
    print(f"Best algorithm: {report.get('best_path')}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Run the baseline GA over a grid of instances x seeds in parallel.

Usage: python solve_parallel.py <out.json> <iid,iid,...> <seeds...>
"""
import importlib.util
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

BASE = Path(r"C:\kares_main\algorithms\baseline\uav_firefighting_soga.py")
EX = Path(r"C:\kares_main\instances\firefighting_instance\example")


def _worker(args):
    iid, seed = args
    spec = importlib.util.spec_from_file_location("baseline_soga", BASE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from solve import run_one
    return run_one(mod, iid, seed)


def main():
    out_path = Path(sys.argv[1])
    iids = [int(x) for x in sys.argv[2].split(",")]
    seeds = [int(x) for x in sys.argv[3].split(",")]
    jobs = [(i, s) for i in iids for s in seeds]
    workers = max(1, min(8, (os.cpu_count() or 2) - 1, len(jobs)))
    print(f"jobs={len(jobs)} workers={workers}", flush=True)

    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_worker, j): j for j in jobs}
        for k, fut in enumerate(as_completed(futs), 1):
            iid, seed = futs[fut]
            try:
                r = fut.result()
                print(f"[{k}/{len(jobs)}] iid={iid} seed={seed} fit={r['fitness']:.2f} "
                      f"fires={r['completed_fires']} cv={r['constraint_violation']} "
                      f"t={r['seconds']}s", flush=True)
                results.append(r)
            except Exception as exc:  # noqa: BLE001
                print(f"[{k}/{len(jobs)}] iid={iid} seed={seed} FAILED: {exc!r}", flush=True)
            results.sort(key=lambda d: (d["instance_id"], d["seed"]))
            out_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    print("written:", out_path, "results:", len(results))


if __name__ == "__main__":
    main()

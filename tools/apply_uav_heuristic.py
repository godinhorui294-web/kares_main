# -*- coding: utf-8 -*-
"""把 ReEvo / EoH 生成的启发式文件应用到 30 条 UAV 实例上。

用法:
    python tools/apply_uav_heuristic.py --heuristic <生成.py> --tag reevo
    python tools/apply_uav_heuristic.py --eoh-samples <.../samples_best.json> --tag eoh
"""
import argparse
import importlib.util
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import uav_ff_common as C  # noqa: E402

OUT_DIR = os.path.join(C.ROOT, "outputs", "llm_heuristic_eval")


def load_select_fn(source_path):
    spec = importlib.util.spec_from_file_location("__uav_heuristic__", source_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    names = [n for n in dir(module) if re.match(r"^select_next_fire(_v\d+)?$", n)]
    if not names:
        raise RuntimeError("no select_next_fire* function found in %s" % source_path)
    names.sort(key=lambda n: (n != "select_next_fire", n != "select_next_fire_v2"))
    return getattr(module, names[0]), names[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--heuristic", help="包含 select_next_fire 的 .py 文件")
    parser.add_argument("--eoh-samples", help="EoH 的 samples_best.json")
    parser.add_argument("--tag", default="heuristic")
    parser.add_argument("--out", default="")
    parser.add_argument("--limit", type=int, default=0, help="只评测前 N 条实例，0 表示 30 条")
    args = parser.parse_args()

    if args.eoh_samples:
        with open(args.eoh_samples, "r", encoding="utf-8") as f:
            sample = json.load(f)
        code = sample.get("code")
        if not code:
            raise SystemExit("no code in %s" % args.eoh_samples)
        os.makedirs(OUT_DIR, exist_ok=True)
        source_path = os.path.join(OUT_DIR, "%s_best.py" % args.tag)
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(code)
        print("extracted heuristic ->", source_path)
    elif args.heuristic:
        source_path = args.heuristic
    else:
        raise SystemExit("need --heuristic or --eoh-samples")

    select_fn, fn_name = load_select_fn(source_path)
    print("using function:", fn_name, "from", source_path)

    paths = C.instance_paths()
    if args.limit:
        paths = paths[:args.limit]
    results = C.evaluate_many(paths, select_fn, strict=False)

    groups = {"25f": [], "10f": [], "50f": []}
    for r in results:
        name = r["instance"]
        if "10f" in name:
            groups["10f"].append(r)
        elif "50f" in name:
            groups["50f"].append(r)
        else:
            groups["25f"].append(r)
    groups = {k: v for k, v in groups.items() if v}
    for group, rows in groups.items():
        print("--- %s ---" % group)
        for r in rows:
            if r.get("fitness") is None:
                print("%-36s FAILED  %s" % (r["instance"], r.get("error")))
            else:
                print("%-36s fitness=%9.2f completed=%s viol=%s makespan=%.1f fallbacks=%s"
                      % (r["instance"], r["fitness"], r.get("completed_fires"),
                         r.get("constraint_violation"), r.get("makespan"), r.get("fallbacks")))

    print("\n=== SUMMARY ===")
    summary = {}
    all_values = []
    for group, rows in groups.items():
        values = [r["fitness"] for r in rows if r.get("fitness") is not None]
        all_values.extend(values)
        if values:
            summary[group] = {"mean": statistics.mean(values), "min": min(values),
                              "max": max(values), "ok": len(values)}
            print("%-4s ok=%2d/%2d mean=%9.2f min=%9.2f max=%9.2f"
                  % (group, len(values), len(rows), summary[group]["mean"],
                     summary[group]["min"], summary[group]["max"]))
        else:
            summary[group] = {"mean": None, "ok": 0}
            print("%-4s ok= 0/%2d" % (group, len(rows)))
    if all_values:
        summary["all"] = {"mean": statistics.mean(all_values), "std": statistics.pstdev(all_values),
                          "min": min(all_values), "max": max(all_values), "ok": len(all_values)}
        print("ALL  ok=%2d/%2d mean=%9.2f std=%9.2f" % (len(all_values), len(results),
                                                       summary["all"]["mean"], summary["all"]["std"]))

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = args.out or os.path.join(OUT_DIR, "%s_results.json" % args.tag)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"tag": args.tag, "source": os.path.abspath(source_path),
                   "function": fn_name, "summary": summary, "results": results},
                  f, ensure_ascii=False, indent=2)
    print("saved ->", out_path)


if __name__ == "__main__":
    main()

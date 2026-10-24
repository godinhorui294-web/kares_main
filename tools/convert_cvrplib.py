#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
convert_cvrplib.py — Convert CVRPLib TSPLIB format (.vrp) files to the JSON
instances used by the KARES pipeline.

Usage:
    python tools/convert_cvrplib.py <input.vrp> <output.json>
    python tools/convert_cvrplib.py --batch <input_dir> <output_dir>   # batch convert .vrp -> .json

Supported EDGE_WEIGHT_TYPE:
  - EUC_2D (round) / CEIL_2D (ceil) / EXACT_2D (float) / FLOOR_2D (floor):
    distances computed from node coordinates
  - EXPLICIT: distance matrix read directly from EDGE_WEIGHT_SECTION
    Supported EDGE_WEIGHT_FORMAT: FULL_MATRIX / UPPER_ROW / LOWER_ROW /
    UPPER_DIAG_ROW / LOWER_DIAG_ROW
The optimal value published by CVRPLib is extracted from the COMMENT line via
regex; null when extraction fails. The distance matrix is precomputed and
written into the JSON so algorithms can do table lookups (index = id - 1).
"""
import argparse
import json
import math
import os
import re

# Section headers in .vrp files (matched in uppercase)
_SECTIONS = (
    "NODE_COORD_SECTION", "DEMAND_SECTION", "DEPOT_SECTION",
    "EDGE_WEIGHT_SECTION", "FIXED_EDGES_SECTION",
    "DISPLAY_DATA_SECTION", "TOUR_SECTION", "EDGE_DATA_SECTION",
)


def _parse_vrp(text):
    """Parse TSPLIB CVRP text; returns (header, nodes, demands, depots, edge_weights)."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    header = {}
    nodes = {}        # id -> (x, y)
    demands = {}      # id -> demand
    depots = []       # depot ids
    edge_weights = [] # flat value stream of the EXPLICIT distance matrix
    section = None

    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper == "EOF":
            break
        # switch section
        if upper in _SECTIONS:
            section = upper
            continue
        if section is None:
            # header key/value pairs like NAME: xxx
            if ":" in line:
                key, _, val = line.partition(":")
                header[key.strip().upper()] = val.strip()
            continue
        # parse data lines per section
        parts = line.split()
        if section == "NODE_COORD_SECTION":
            if len(parts) >= 3:
                try:
                    nid = int(parts[0])
                    x = float(parts[1])
                    y = float(parts[2])
                    nodes[nid] = (x, y)
                except ValueError:
                    continue
        elif section == "DEMAND_SECTION":
            if len(parts) >= 2:
                try:
                    nid = int(parts[0])
                    demands[nid] = int(float(parts[1]))
                except ValueError:
                    continue
        elif section == "DEPOT_SECTION":
            for p in parts:
                try:
                    v = int(p)
                except ValueError:
                    continue
                if v == -1:
                    break
                depots.append(v)
        elif section == "EDGE_WEIGHT_SECTION":
            # EXPLICIT mode: collect all numbers in order of appearance
            for p in parts:
                try:
                    edge_weights.append(float(p))
                except ValueError:
                    continue
        # remaining sections are unused
    return header, nodes, demands, depots, edge_weights


def _distance(x1, y1, x2, y2, ewt):
    d = math.hypot(x1 - x2, y1 - y2)
    if ewt == "EUC_2D":
        return int(round(d))
    if ewt == "CEIL_2D":
        return int(math.ceil(d))
    if ewt == "FLOOR_2D":
        return int(math.floor(d))
    if ewt == "EXACT_2D":
        return d
    raise ValueError(f"Unsupported EDGE_WEIGHT_TYPE: {ewt} (only EUC_2D/CEIL_2D/EXACT_2D/FLOOR_2D/EXPLICIT are supported)")


def _build_explicit_matrix(stream, n, fmt):
    """
    Build an n x n symmetric matrix from an EXPLICIT distance stream.
    fmt in {FULL_MATRIX, UPPER_ROW, LOWER_ROW, UPPER_DIAG_ROW, LOWER_DIAG_ROW}:
      - FULL_MATRIX: n*n values, row-major
      - UPPER_ROW: upper triangle without the diagonal, row i column j>i; n*(n-1)/2 values
      - LOWER_ROW: lower triangle without the diagonal, row i column j<i; n*(n-1)/2 values
      - UPPER_DIAG_ROW / LOWER_DIAG_ROW: including the diagonal, n*(n+1)/2 values
    """
    dm = [[0] * n for _ in range(n)]
    k = 0
    L = len(stream)

    def take():
        nonlocal k
        if k >= L:
            raise ValueError(f"EDGE_WEIGHT stream too short: need >= {k+1}, got {L}")
        v = stream[k]
        k += 1
        return v

    fmt_up = (fmt or "").upper().strip()
    if fmt_up == "FULL_MATRIX":
        for i in range(n):
            for j in range(n):
                dm[i][j] = take()
    elif fmt_up == "UPPER_ROW":
        for i in range(n - 1):
            for j in range(i + 1, n):
                v = take()
                dm[i][j] = v
                dm[j][i] = v
    elif fmt_up == "LOWER_ROW":
        for i in range(1, n):
            for j in range(0, i):
                v = take()
                dm[i][j] = v
                dm[j][i] = v
    elif fmt_up == "UPPER_DIAG_ROW":
        for i in range(n):
            for j in range(i, n):
                v = take()
                dm[i][j] = v
                dm[j][i] = v
    elif fmt_up == "LOWER_DIAG_ROW":
        for i in range(n):
            for j in range(0, i + 1):
                v = take()
                dm[i][j] = v
                dm[j][i] = v
    else:
        raise ValueError(f"Unsupported EDGE_WEIGHT_FORMAT: {fmt}")
    return dm


def _extract_optimal(header):
    """Extract the optimal value from the COMMENT line. Common CVRPLib forms: (Optimal value: 375) / Optimal solution: 820"""
    comment = header.get("COMMENT", "")
    patterns = [
        r"[Oo]ptimal\s*(?:value|solution)?\s*[:：]?\s*(\d+(?:\.\d+)?)",
        r"\(\s*[Oo]ptimal\s*[:：]?\s*(\d+(?:\.\d+)?)\s*\)",
    ]
    for pat in patterns:
        m = re.search(pat, comment)
        if m:
            v = m.group(1)
            f = float(v)
            return int(f) if f.is_integer() else f
    return None


def convert(vrp_path, json_path=None):
    with open(vrp_path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    header, nodes, demands, depots, edge_weights = _parse_vrp(text)

    name = header.get("NAME", os.path.splitext(os.path.basename(vrp_path))[0])
    ewt = header.get("EDGE_WEIGHT_TYPE", "EUC_2D")
    dimension = int(header.get("DIMENSION", len(nodes)))
    capacity = int(float(header.get("CAPACITY", 0)))
    depot_id = depots[0] if depots else 1

    # EXPLICIT mode: nodes may carry no coordinates; fill the id list with 1..dimension
    explicit = ewt.upper() == "EXPLICIT"
    if explicit:
        ids = list(range(1, dimension + 1))
        if len(nodes) != dimension:
            # missing coordinates default to (0, 0); distance_matrix is authoritative
            for nid in ids:
                if nid not in nodes:
                    nodes[nid] = (0.0, 0.0)
    else:
        ids = sorted(nodes.keys())
        if len(ids) != dimension:
            print(f"[WARN] {name}: DIMENSION={dimension} but found {len(ids)} nodes; using the actual count")
            dimension = len(ids)

    # Build the distance matrix
    if explicit:
        fmt = header.get("EDGE_WEIGHT_FORMAT", "FULL_MATRIX")
        dm = _build_explicit_matrix(edge_weights, dimension, fmt)
    else:
        dm = [[0] * dimension for _ in range(dimension)]
        for i in range(dimension):
            xi, yi = nodes[ids[i]]
            for j in range(i + 1, dimension):
                xj, yj = nodes[ids[j]]
                d = _distance(xi, yi, xj, yj, ewt)
                dm[i][j] = d
                dm[j][i] = d

    node_list = []
    for nid in ids:
        x, y = nodes.get(nid, (0.0, 0.0))
        node_list.append({
            "id": nid,
            "x": x,
            "y": y,
            "demand": demands.get(nid, 0),
            "is_depot": (nid == depot_id),
        })

    out = {
        "instance_id": name,
        "name": name,
        "problem_type": "cvrp",
        "dimension": dimension,
        "num_customers": dimension - 1,
        "capacity": capacity,
        "edge_weight_type": ewt,
        "depot_id": depot_id,
        "optimal": _extract_optimal(header),
        "nodes": node_list,
        "distance_matrix": dm,
    }

    if json_path is None:
        json_path = os.path.splitext(vrp_path)[0] + ".json"
    out_dir = os.path.dirname(os.path.abspath(json_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return json_path, out


def main():
    ap = argparse.ArgumentParser(description="CVRPLib .vrp -> JSON converter")
    ap.add_argument("input", help="Input .vrp file (or input directory with --batch)")
    ap.add_argument("output", nargs="?", help="Output .json file (or output directory with --batch)")
    ap.add_argument("--batch", action="store_true", help="Batch-convert every .vrp file in the directory")
    args = ap.parse_args()

    if args.batch:
        in_dir = args.input
        out_dir = args.output or in_dir
        os.makedirs(out_dir, exist_ok=True)
        count = 0
        for fn in sorted(os.listdir(in_dir)):
            if fn.lower().endswith(".vrp"):
                in_path = os.path.join(in_dir, fn)
                out_path = os.path.join(out_dir, os.path.splitext(fn)[0] + ".json")
                _, out = convert(in_path, out_path)
                print(f"  {fn} -> dim={out['dimension']} cap={out['capacity']} "
                      f"opt={out['optimal']} nodes={len(out['nodes'])}")
                count += 1
        print(f"Conversion done: {count} file(s) -> {out_dir}")
    else:
        if not args.output:
            ap.error("single-file mode requires an output path")
        _, out = convert(args.input, args.output)
        print(f"Conversion done: {args.input} -> {args.output}")
        print(f"  dimension={out['dimension']} capacity={out['capacity']} "
              f"optimal={out['optimal']} nodes={len(out['nodes'])}")


if __name__ == "__main__":
    main()

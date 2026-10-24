# -*- coding: utf-8 -*-
"""LLM 调用用量记录：每次调用的 token 数与耗时，以及按迭代/整体的汇总。

ReEvo 与 EoH 的框架代码通过可选 import 调用本模块；若未配置输出路径，
仍然会在内存中累计，便于运行结束时统一汇总。
"""
import json
import os
import threading
import time

_lock = threading.Lock()
_calls = []          # 每次调用: {idx, ts, elapsed, prompt, completion, total, model, algorithm, iteration}
_path = None
_context = {"algorithm": "", "iteration": None}


def configure(path):
    """设置 JSONL 输出路径（每次调用一行），并清空已有文件。"""
    global _path
    with _lock:
        _path = path
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
    return path


def set_context(algorithm=None, iteration=None):
    """设置当前上下文（用于给并发外的调用打上算法名/迭代号）。"""
    with _lock:
        if algorithm is not None:
            _context["algorithm"] = algorithm
        _context["iteration"] = iteration


def record(prompt_tokens=0, completion_tokens=0, total_tokens=0, elapsed=0.0,
           model="", algorithm=None, iteration=None):
    """记录一次 LLM 调用。返回该条记录。"""
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    total_tokens = int(total_tokens or (prompt_tokens + completion_tokens))
    with _lock:
        entry = {
            "idx": len(_calls),
            "ts": round(time.time(), 3),
            "elapsed": round(float(elapsed or 0.0), 3),
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": total_tokens,
            "model": model or "",
            "algorithm": algorithm if algorithm is not None else _context["algorithm"],
            "iteration": iteration if iteration is not None else _context["iteration"],
        }
        _calls.append(entry)
        if _path:
            try:
                with open(_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError:
                pass
    return entry


def mark():
    """返回当前调用计数，用作 stats_since 的起点。"""
    with _lock:
        return len(_calls)


def _aggregate(rows):
    return {
        "calls": len(rows),
        "prompt_tokens": sum(r["prompt"] for r in rows),
        "completion_tokens": sum(r["completion"] for r in rows),
        "total_tokens": sum(r["total"] for r in rows),
        "llm_time": round(sum(r["elapsed"] for r in rows), 1),
    }


def stats_since(index):
    with _lock:
        rows = list(_calls[index:])
    return _aggregate(rows)


def stats_total():
    with _lock:
        rows = list(_calls)
    return _aggregate(rows)


def format_stats(stats):
    return ("calls=%d prompt_tokens=%d completion_tokens=%d total_tokens=%d llm_time=%.1fs"
            % (stats["calls"], stats["prompt_tokens"], stats["completion_tokens"],
               stats["total_tokens"], stats["llm_time"]))


def write_summary(path, extra=None):
    """把整体汇总（以及可选的逐迭代汇总）写入 JSON 文件。"""
    stats = stats_total()
    payload = {"total": stats, "per_call_log": _path}
    if extra:
        payload.update(extra)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return payload

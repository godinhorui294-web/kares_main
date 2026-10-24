"""
kares_workflow.diversity_filter — two-level hash fingerprint dedup
(structural + logical).

Structural hash: hash of the normalized AST skeleton (docstrings/comments/
literal detail stripped), capturing the operator-framework structure.
Logical hash: hash of the serialized AST node sequence of each function or
method body, capturing implementation differences.

A candidate counts as a duplicate only when both hashes match.
"""
import ast
import hashlib
from typing import Dict


def _norm_ast(tree: ast.AST) -> ast.AST:
    """Normalize the AST by stripping docstrings."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    return tree


def structural_hash(code: str) -> str:
    """Structural hash: class/function definition skeleton only (names +
    nesting); method bodies are ignored."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "SYNTAX_ERROR:" + hashlib.md5(code.encode("utf-8")).hexdigest()[:12]

    skeleton = []

    def _walk(node, depth=0):
        if isinstance(node, ast.ClassDef):
            skeleton.append(f"{'  '*depth}CLASS:{node.name}")
            for child in node.body:
                _walk(child, depth + 1)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # structural level records method names and arity only
            nargs = len(node.args.args)
            skeleton.append(f"{'  '*depth}DEF:{node.name}({nargs})")
            # do not descend into method bodies (internal logic is out of scope here)

    for node in tree.body:
        _walk(node, 0)
    return hashlib.md5("\n".join(skeleton).encode("utf-8")).hexdigest()[:16]


def logical_hash(code: str) -> str:
    """Logical hash: hash of each method body's AST node-type sequence, reflecting implementation differences."""
    try:
        tree = _norm_ast(ast.parse(code))
    except SyntaxError:
        return "SYNTAX_ERROR:" + hashlib.md5(code.encode("utf-8")).hexdigest()[:12]

    bodies = []

    def _body_signature(node):
        # serialize the type names of all nodes in the body
        sig = []
        for n in ast.walk(node):
            sig.append(type(n).__name__)
        return hashlib.md5("|".join(sig).encode("utf-8")).hexdigest()[:16]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bodies.append(f"{node.name}:{_body_signature(node)}")
    return hashlib.md5(";".join(bodies).encode("utf-8")).hexdigest()[:16]


class DiversityFilter:
    """Algorithm-pool dedup based on two-level hashing."""

    def __init__(self):
        self.seen: list = []  # [{struct: str, logic: str, path: str}]

    def fingerprint(self, code: str) -> Dict[str, str]:
        return {"struct": structural_hash(code), "logic": logical_hash(code)}

    def is_duplicate(self, code: str) -> bool:
        fp = self.fingerprint(code)
        for s in self.seen:
            if s["struct"] == fp["struct"] and s["logic"] == fp["logic"]:
                return True
        return False

    def register(self, code: str, path: str = ""):
        fp = self.fingerprint(code)
        fp["path"] = path
        self.seen.append(fp)

    def reset(self):
        self.seen = []

"""Shared utilities for code generators: extract_code / _parse_header."""
import re
from typing import List, Optional, Tuple


_CODE_BLOCK_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> Optional[str]:
    """Extract the first ```python block from LLM output; fall back to the
    whole text when it looks like raw code (contains class/def)."""
    if not text:
        return None
    m = _CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    if "class " in text and "def " in text:
        return text.strip()
    return None


# Knowledge declaration: "# Borrowed knowledge: [K_p_KB-001, K_p_KB-007]"
# (the bracketed list form or a bare comma-separated form are both accepted)
_KID_LIST_RE = re.compile(r"Borrowed\s+knowledge\s*[:：]\s*\[([^\]]*)\]", re.IGNORECASE)
_KID_BARE_RE = re.compile(r"Borrowed\s+knowledge\s*[:：]\s*([^\n\]]+)", re.IGNORECASE)
_KID_TOKEN_RE = re.compile(r"K_[pwps]_[A-Za-z0-9_\-]+")


def _parse_knowledge_ids(head: str) -> List[str]:
    """Extract declared knowledge node ids from the header comment."""
    ids: List[str] = []
    m = _KID_LIST_RE.search(head)
    text = m.group(1) if m else None
    if text is None:
        m2 = _KID_BARE_RE.search(head)
        text = m2.group(1) if m2 else None
    if text:
        ids = _KID_TOKEN_RE.findall(text)
    seen, out = set(), []
    for k in ids:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _parse_header(code: str) -> Tuple[str, str, List[str]]:
    """Extract algorithm name, innovation summary and declared knowledge ids
    from the header comment.

    Returns (name, innovation, knowledge_ids). Empty knowledge_ids means the
    LLM did not declare any (callers should fall back to the full retrieval set).
    """
    name = "algo"
    innovation = ""
    head = code[:800]
    m = re.search(r"Algorithm\s+name\s*[:：]\s*(.+)", head, re.IGNORECASE)
    if m:
        name = re.sub(r"[^\w]", "_", m.group(1).strip())[:30] or "algo"
    m = re.search(r"Innovation\s*[:：]\s*(.+)", head, re.IGNORECASE)
    if m:
        innovation = m.group(1).strip()
    knowledge_ids = _parse_knowledge_ids(head)
    # Fallback: first class name
    if name == "algo":
        m = re.search(r"^class\s+(\w+)", code, re.MULTILINE)
        if m:
            name = re.sub(r"[^\w]", "_", m.group(1))[:30]
    return name, innovation, knowledge_ids

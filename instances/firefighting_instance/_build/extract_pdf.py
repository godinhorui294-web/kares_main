# -*- coding: utf-8 -*-
"""Extract text from the reference paper PDF for style analysis."""
import sys
from pathlib import Path

import fitz

PDF = Path(r"C:\Users\10436\.dsh\attachments\v1\files\56\563e374ca154a631d2bb22c839d0d382dd9cbaf387d6f0312b2f75d49a3f0ad6\Zhang 等 - 2023 - Dynamic Mission Planning Algorithm for UAV Formation in Battlefield Environment.no_watermark.zh-CN.dual.pdf")
OUT = Path(__file__).resolve().parent / "paper_text.txt"

doc = fitz.open(PDF)
print("pages:", doc.page_count)
print("metadata:", {k: v for k, v in doc.metadata.items() if v})

chunks = []
for i, page in enumerate(doc):
    chunks.append(f"\n\n===== PAGE {i + 1} =====\n")
    chunks.append(page.get_text("text"))

text = "".join(chunks)
OUT.write_text(text, encoding="utf-8")
print("chars:", len(text))
print("written:", OUT)

import fitz
import sys

try:
    doc = fitz.open("c:/GenAI/ewa-mcp/tmp-smoke.pdf")
    for i in range(min(5, len(doc))):
        print(f"--- PAGE {i+1} ---")
        print(doc[i].get_text())
except Exception as e:
    print(e)

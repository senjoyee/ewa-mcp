import fitz
import re

pdf_path = r"c:\GenAI\ewa-mcp\Files\ERP_EWA_02.2026.pdf"
doc = fitz.open(pdf_path)
text = doc[0].get_text("text", sort=True)
doc.close()

metadata = {}

# Regex patterns for new text format
patterns = {
    "sid": r"SAP System ID\s+([A-Z0-9]{3})",
    "product": r"Product\s+(.+)$",
    "status": r"Status\s+(.+)$",
    "db_system": r"DB System\s+(.+)$",
    "analysis_from": r"Analysis from\s+(\d{2}\.\d{2}\.\d{4})",
    "analysis_to": r"Until\s+(\d{2}\.\d{2}\.\d{4})",
    "session_no": r"Session No\.\s+(\d+)",
    "installation_no": r"Installation No\.\s+(\d+)"
}

print("EXTRACTION RESULTS:")
for key, pattern in patterns.items():
    match = re.search(pattern, text, re.MULTILINE)
    if match:
        metadata[key] = match.group(1).strip()
        print(f"[{key}]: {metadata[key]}")
    else:
        print(f"[{key}]: NOT FOUND")

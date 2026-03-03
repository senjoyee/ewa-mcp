import fitz
import pymupdf4llm

pdf_path = r"c:\GenAI\ewa-mcp\Files\ERP_EWA_02.2026.pdf"
doc = fitz.open(pdf_path)

print("--- get_text('text', sort=True) ---")
print(doc[0].get_text("text", sort=True))


print("\n--- pymupdf4llm ---")
md = pymupdf4llm.to_markdown(doc, pages=[0])
print(md)

doc.close()

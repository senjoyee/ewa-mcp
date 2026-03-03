import logging
import json
from processor.extractors.pdf_extractor import PDFExtractor

logging.basicConfig(level=logging.INFO)

try:
    extractor = PDFExtractor()
    
    pdf_path = r"c:\GenAI\ewa-mcp\Files\ERP_EWA_02.2026.pdf"
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
            
    print("Running PDF Extractor...")
    document, markdown_text, priority_images = extractor.extract(pdf_bytes, "cust1", "ERP_EWA_02.2026.pdf")
    
    print("--- Document Metadata ---")
    print(f"SID: {document.sid}")
    print(f"Product: {document.product}")
    print(f"DB System: {document.db_system}")
    print(f"Installation No: {document.installation_no}")
    print(f"Analysis From: {document.analysis_from}")
    print(f"Analysis To: {document.analysis_to}")

except Exception as e:
    logging.exception("Failed")

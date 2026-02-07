"""PDF text extraction using pymupdf4llm."""

import hashlib
import io
from typing import Tuple
from datetime import datetime
import fitz  # PyMuPDF
import pymupdf4llm

from shared.models.document import Document


class PDFExtractor:
    """Extract text and metadata from EWA PDFs."""
    
    def __init__(self):
        self.priority_pages = [0, 1, 2, 3]  # Pages 1-4 (0-indexed)
    
    def extract(self, pdf_bytes: bytes, customer_id: str, file_name: str) -> Tuple[Document, str, list]:
        """Extract document metadata, full markdown, and priority page images.
        
        Args:
            pdf_bytes: Raw PDF file bytes
            customer_id: Customer tenant ID
            file_name: Original filename
            
        Returns:
            Tuple of (Document metadata, full markdown text, list of priority page images as bytes)
        """
        # Calculate hash
        sha256_hash = hashlib.sha256(pdf_bytes).hexdigest()
        
        # Open PDF with PyMuPDF
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        # Extract metadata
        pages = len(doc)
        doc_id = f"{customer_id}_{sha256_hash[:16]}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Try to extract SID from filename or first page
        sid = self._extract_sid(file_name, doc)
        
        # Create document model
        document = Document(
            doc_id=doc_id,
            customer_id=customer_id,
            sid=sid,
            file_name=file_name,
            pages=pages,
            sha256=sha256_hash,
            processing_status="extracting"
        )
        
        # Extract full markdown
        markdown_text = pymupdf4llm.to_markdown(doc)
        
        # Extract priority page images (pages 1-4)
        priority_images = []
        for page_num in self.priority_pages:
            if page_num < pages:
                page = doc[page_num]
                # Render at higher resolution for better OCR
                mat = fitz.Matrix(2, 2)  # 2x zoom
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                priority_images.append(img_bytes)
        
        doc.close()
        
        return document, markdown_text, priority_images
    
    def _extract_sid(self, file_name: str, doc: fitz.Document) -> str:
        """Extract SAP System ID from filename or document."""
        # Try filename patterns first
        import re
        patterns = [
            r'[A-Z]{3}\d{3}',  # Standard SID pattern (e.g., PRD001)
            r'[A-Z]{3}_\w+',   # Pattern with underscore
        ]
        for pattern in patterns:
            match = re.search(pattern, file_name.upper())
            if match:
                return match.group(0)
        
        # Try first page text
        if len(doc) > 0:
            text = doc[0].get_text()
            match = re.search(r'System\s*[:\-]?\s*([A-Z]{3}\d{3})', text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return "UNKNOWN"


def extract_page_as_image(doc: fitz.Document, page_num: int, zoom: float = 2.0) -> bytes:
    """Extract a single page as PNG image bytes.
    
    Args:
        doc: PyMuPDF document
        page_num: Page number (0-indexed)
        zoom: Zoom factor for resolution
        
    Returns:
        PNG image bytes
    """
    if page_num >= len(doc):
        raise ValueError(f"Page {page_num} does not exist in document")
    
    page = doc[page_num]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")

"""PDF text extraction using pymupdf4llm."""

import hashlib
import re
from typing import Tuple
from datetime import datetime
import fitz  # PyMuPDF
import pymupdf4llm

from models.document import Document


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
        doc_id = f"{customer_id}_{sha256_hash[:16]}"
        first_page_text = doc[0].get_text() if pages > 0 else ""
        
        # Extract deterministic cover-page metadata
        sid = self._extract_sid(first_page_text)
        analysis_from, analysis_to = self._extract_analysis_window(first_page_text)
        
        # Create document model
        document = Document(
            doc_id=doc_id,
            customer_id=customer_id,
            sid=sid,
            analysis_from=analysis_from,
            analysis_to=analysis_to,
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
    
    def _extract_sid(self, first_page_text: str) -> str:
        """Extract SAP SID from page-1 label/value pairs only.

        This intentionally avoids permissive filename-based guessing to prevent hallucinated values.
        """
        text = (first_page_text or "").upper()
        if not text:
            return "UNKNOWN"

        sid_patterns = [
            r"\bSID\b\s*[:\-]?\s*([A-Z0-9]{3})\b",
            r"\bSYSTEM\s+ID\b\s*[:\-]?\s*([A-Z0-9]{3})\b",
            r"\bSYSTEM\b\s*[:\-]?\s*([A-Z0-9]{3})\b",
        ]

        for pattern in sid_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return "UNKNOWN"

    def _extract_analysis_window(self, first_page_text: str) -> Tuple[datetime | None, datetime | None]:
        """Extract analysis period start/end dates from page 1 text."""
        text = (first_page_text or "")
        if not text:
            return None, None

        # Common EWA/cover-page variants.
        patterns = [
            r"analysis\s*(?:period)?\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*(?:to|\-|–|—)\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"analysis\s*from\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}).{0,30}?analysis\s*(?:to|until)\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
            r"from\s*[:\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\s*(?:to|\-|–|—)\s*(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if not match:
                continue

            start = self._parse_date(match.group(1))
            end = self._parse_date(match.group(2))
            if start and end:
                return start, end

        return None, None

    @staticmethod
    def _parse_date(raw: str) -> datetime | None:
        """Parse a date string from common EWA formats."""
        if not raw:
            return None

        text = raw.strip().replace("/", ".").replace("-", ".")
        parts = text.split(".")
        if len(parts) == 3 and len(parts[2]) == 2:
            # Interpret yy as 20yy for current EWA documents.
            text = f"{parts[0]}.{parts[1]}.20{parts[2]}"

        for fmt in ("%d.%m.%Y", "%Y.%m.%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None


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

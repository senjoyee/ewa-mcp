"""PDF text extraction using pymupdf4llm."""

import hashlib
import re
from typing import Tuple
from datetime import datetime, date
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
        first_page_text = doc[0].get_text("text", sort=True) if pages > 0 else ""
        
        # Extract deterministic cover-page metadata
        sid = self._extract_field(first_page_text, r"SAP System ID\s+([A-Z0-9]{3})", default="UNKNOWN")
        analysis_from, analysis_to = self._extract_analysis_window(first_page_text)
        
        product = self._extract_field(first_page_text, r"Product\s+(.+)$")
        db_system = self._extract_field(first_page_text, r"DB System\s+(.+)$")
        installation_no = self._extract_field(first_page_text, r"Installation No\.\s+(\d+)")
        
        date_str = analysis_to.strftime("%m%d%Y") if analysis_to else "UNKNOWN_DATE"
        doc_id = f"{customer_id}_{sid}_{date_str}"
        
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
            product=product,
            db_system=db_system,
            installation_no=installation_no,
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
    
    def _extract_field(self, first_page_text: str, pattern: str, default: str = None) -> str | None:
        """Extract a field using regex from page-1 text."""
        text = (first_page_text or "")
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return default

    def _extract_analysis_window(self, first_page_text: str) -> Tuple[date | None, date | None]:
        """Extract analysis period start/end dates from page 1 text using `sort=True` layout."""
        text = (first_page_text or "")
        if not text:
            return None, None
            
        start_match = re.search(r"Analysis from\s+(\d{2}\.\d{2}\.\d{4})", text, re.MULTILINE)
        end_match = re.search(r"Until\s+(\d{2}\.\d{2}\.\d{4})", text, re.MULTILINE)
        
        start = self._parse_date(start_match.group(1)).date() if start_match and self._parse_date(start_match.group(1)) else None
        end = self._parse_date(end_match.group(1)).date() if end_match and self._parse_date(end_match.group(1)) else None
        
        return start, end

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

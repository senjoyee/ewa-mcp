"""Markdown header-based chunking for EWA documents."""

import re
import uuid
from typing import List, Tuple, Optional
from datetime import datetime

from shared.models.chunk import Chunk
from shared.models.alert import Alert, Severity, Category


class MarkdownChunker:
    """Chunk markdown content by headers while preserving hierarchy."""
    
    def __init__(self, max_chunk_size: int = 4000):
        """Initialize chunker.
        
        Args:
            max_chunk_size: Maximum characters per chunk
        """
        self.max_chunk_size = max_chunk_size
        self.header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    
    def chunk_document(
        self,
        markdown: str,
        doc_id: str,
        customer_id: str,
        sid: str,
        environment: str = None,
        report_date: datetime = None,
        page_map: List[Tuple[int, int, str]] = None
    ) -> List[Chunk]:
        """Chunk markdown document by headers.
        
        Args:
            markdown: Full markdown text
            doc_id: Document ID
            customer_id: Customer tenant ID
            sid: SAP System ID
            environment: System environment
            report_date: Report generation date
            page_map: List of (start_char, end_char, page_num) for tracking pages
            
        Returns:
            List of Chunk objects
        """
        chunks = []
        
        # Split by headers
        sections = self._split_by_headers(markdown)
        
        for i, (header_level, header_text, content, start_pos, end_pos) in enumerate(sections):
            # Build section path
            section_path = self._build_section_path(sections, i, header_level, header_text)
            
            # Determine page range from position
            page_start, page_end = self._get_page_range(start_pos, end_pos, page_map)
            
            # Generate chunk ID
            chunk_id = f"{doc_id}_chunk_{i:04d}"
            
            # Extract metadata from content
            severity = self._extract_severity(content, header_text)
            category = self._extract_category(content, header_text)
            sap_notes = self._extract_sap_notes(content)
            
            # Create chunk
            chunk = Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                customer_id=customer_id,
                sid=sid,
                environment=environment,
                report_date=report_date,
                section_path=section_path,
                page_start=page_start,
                page_end=page_end,
                severity=severity,
                category=category,
                sap_note_ids=sap_notes,
                content_md=f"{'#' * header_level} {header_text}\n\n{content}".strip() if header_level > 0 else content,
                header_level=header_level if header_level > 0 else None
            )
            
            # Split if too large
            if len(chunk.content_md) > self.max_chunk_size:
                sub_chunks = self._split_large_chunk(chunk, i)
                chunks.extend(sub_chunks)
            else:
                chunks.append(chunk)
        
        return chunks
    
    def _split_by_headers(self, markdown: str) -> List[Tuple[int, str, str, int, int]]:
        """Split markdown into sections by headers.
        
        Returns list of (header_level, header_text, content, start_pos, end_pos)
        """
        matches = list(self.header_pattern.finditer(markdown))
        
        if not matches:
            # No headers found - treat entire document as one chunk
            return [(0, "Document", markdown, 0, len(markdown))]
        
        sections = []
        
        # Handle content before first header
        first_match = matches[0]
        if first_match.start() > 0:
            intro = markdown[:first_match.start()].strip()
            if intro:
                sections.append((0, "Introduction", intro, 0, first_match.start()))
        
        # Process each header section
        for i, match in enumerate(matches):
            header_level = len(match.group(1))
            header_text = match.group(2).strip()
            start_pos = match.start()
            
            # Find end of this section (start of next header or end of document)
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(markdown)
            
            content = markdown[match.end():end_pos].strip()
            sections.append((header_level, header_text, content, start_pos, end_pos))
        
        return sections
    
    def _build_section_path(
        self, 
        sections: List[Tuple], 
        current_idx: int, 
        current_level: int,
        current_header: str
    ) -> str:
        """Build hierarchical section path like '1. Overview/1.1 Hardware'."""
        if current_level == 0:
            return current_header
        
        path_parts = []
        
        # Track section numbers at each level
        level_counters = {}
        
        for i in range(current_idx + 1):
            level, header, _, _, _ = sections[i]
            
            if level == 0:
                continue
            
            if level not in level_counters:
                level_counters[level] = 0
            
            level_counters[level] += 1
            
            # Reset deeper levels
            for l in list(level_counters.keys()):
                if l > level:
                    del level_counters[l]
            
            if i == current_idx:
                # Build path for current section
                for l in sorted(level_counters.keys()):
                    if l in level_counters:
                        # Find the header at this level in the chain
                        for j in range(i + 1):
                            lj, hj, _, _, _ = sections[j]
                            if lj == l:
                                if l == current_level:
                                    path_parts.append(f"{level_counters[l]}. {hj}")
                                elif l < current_level:
                                    path_parts.append(f"{level_counters[l]}. {hj}")
                                break
                break
        
        return "/".join(path_parts) if path_parts else current_header
    
    def _get_page_range(
        self, 
        start_pos: int, 
        end_pos: int, 
        page_map: List[Tuple[int, int, str]]
    ) -> Tuple[int, int]:
        """Determine page numbers from character position mapping."""
        if not page_map:
            return (1, 1)
        
        page_start = 1
        page_end = 1
        
        for char_start, char_end, page_num in page_map:
            if start_pos >= char_start and start_pos <= char_end:
                page_start = int(page_num)
            if end_pos >= char_start and end_pos <= char_end:
                page_end = int(page_num)
        
        return (page_start, max(page_start, page_end))
    
    def _extract_severity(self, content: str, header: str) -> Optional[Severity]:
        """Extract severity from content or header."""
        text = (header + " " + content).lower()
        
        if "very high" in text or "critical" in text:
            return Severity.VERY_HIGH
        elif "high" in text:
            return Severity.HIGH
        elif "medium" in text:
            return Severity.MEDIUM
        elif "low" in text:
            return Severity.LOW
        elif "info" in text:
            return Severity.INFO
        
        return None
    
    def _extract_category(self, content: str, header: str) -> Optional[Category]:
        """Extract category from content or header."""
        text = (header + " " + content).lower()
        
        category_map = {
            "security": ["security", "patch", "vulnerability", "audit", "authorization"],
            "performance": ["performance", "response time", "throughput", "cpu", "memory"],
            "stability": ["stability", "crash", "dump", "error", "abap"],
            "configuration": ["configuration", "parameter", "profile", "settings"],
            "lifecycle": ["lifecycle", "support package", "sp", "upgrade", "version"],
            "data_volume": ["data volume", "database size", "growth", "archiving", "table size"],
            "database": ["hana", "oracle", "sql server", "db2", "database"],
            "bw": ["bw", "business warehouse", "infocube", "dso"],
        }
        
        for cat, keywords in category_map.items():
            if any(kw in text for kw in keywords):
                return Category(cat)
        
        return None
    
    def _extract_sap_notes(self, content: str) -> List[str]:
        """Extract SAP note numbers from content."""
        pattern = r'(?:SAP\s*)?[Nn]ote\s*(?:Number\s*)?[:\-]?\s*(\d{7,10})'
        matches = re.findall(pattern, content)
        return list(set(matches))  # Remove duplicates
    
    def _split_large_chunk(self, chunk: Chunk, base_idx: int) -> List[Chunk]:
        """Split a large chunk into smaller sub-chunks."""
        sub_chunks = []
        content = chunk.content_md
        
        # Split by paragraphs while preserving header
        lines = content.split('\n')
        header = lines[0] if lines and lines[0].startswith('#') else ""
        body = '\n'.join(lines[1:]) if header else content
        
        paragraphs = body.split('\n\n')
        current_content = header + "\n\n" if header else ""
        chunk_num = 0
        
        for para in paragraphs:
            if len(current_content) + len(para) > self.max_chunk_size and current_content.strip():
                # Create sub-chunk
                sub_chunk = chunk.model_copy()
                sub_chunk.chunk_id = f"{chunk.doc_id}_chunk_{base_idx:04d}_sub{chunk_num:02d}"
                sub_chunk.content_md = current_content.strip()
                sub_chunk.parent_chunk_id = chunk.chunk_id
                sub_chunks.append(sub_chunk)
                
                current_content = header + "\n\n" + para if header else para
                chunk_num += 1
            else:
                current_content += "\n\n" + para if current_content.strip() else para
        
        # Add remaining content
        if current_content.strip():
            sub_chunk = chunk.model_copy()
            sub_chunk.chunk_id = f"{chunk.doc_id}_chunk_{base_idx:04d}_sub{chunk_num:02d}"
            sub_chunk.content_md = current_content.strip()
            sub_chunk.parent_chunk_id = chunk.chunk_id
            sub_chunks.append(sub_chunk)
        
        return sub_chunks
    
    def link_alerts_to_chunks(self, alerts: List[Alert], chunks: List[Chunk]) -> List[Alert]:
        """Link alerts to their evidence chunks based on page/section overlap."""
        for alert in alerts:
            evidence_ids = []
            
            for chunk in chunks:
                # Match by page range overlap
                page_overlap = (
                    chunk.page_start <= alert.page_end and 
                    chunk.page_end >= alert.page_start
                )
                
                # Or match by severity/category in section path
                section_match = False
                if alert.severity and alert.severity.value in chunk.section_path.lower():
                    section_match = True
                if alert.category and alert.category.value in chunk.section_path.lower():
                    section_match = True
                
                if page_overlap or section_match:
                    evidence_ids.append(chunk.chunk_id)
            
            alert.evidence_chunk_ids = list(set(evidence_ids))[:5]  # Limit to top 5
        
        return alerts

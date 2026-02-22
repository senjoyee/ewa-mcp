"""Azure AI Search client wrapper for MCP tools."""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient as AzureSearchClient
from azure.search.documents.models import (
    VectorizedQuery,
    QueryType,
    SearchMode
)

from shared.models.document import Document
from shared.models.alert import Alert, Severity, Category
from shared.models.chunk import Chunk


class SearchClient:
    """Wrapper for Azure AI Search operations."""
    
    def __init__(self, endpoint: str, api_key: str):
        """Initialize search client.
        
        Args:
            endpoint: Azure AI Search endpoint
            api_key: Azure AI Search API key
        """
        self.endpoint = endpoint
        self.credential = AzureKeyCredential(api_key)
        
        self.docs_index = os.environ.get("INDEX_DOCS", "ewa-docs")
        self.chunks_index = os.environ.get("INDEX_CHUNKS", "ewa-chunks")
        self.alerts_index = os.environ.get("INDEX_ALERTS", "ewa-alerts")
    
    def _get_client(self, index_name: str) -> AzureSearchClient:
        """Get search client for index."""
        return AzureSearchClient(
            endpoint=self.endpoint,
            index_name=index_name,
            credential=self.credential
        )
    
    def _build_filter(self, customer_id: str, **kwargs) -> str:
        """Build OData filter with customer_id and optional filters."""
        filters = [f"customer_id eq '{customer_id}'"]
        
        if kwargs.get("sid"):
            filters.append(f"sid eq '{kwargs['sid']}'")
        if kwargs.get("doc_id"):
            filters.append(f"doc_id eq '{kwargs['doc_id']}'")
        if kwargs.get("date_from"):
            filters.append(f"report_date ge {kwargs['date_from']}T00:00:00Z")
        if kwargs.get("date_to"):
            filters.append(f"report_date le {kwargs['date_to']}T00:00:00Z")
        if kwargs.get("severity"):
            filters.append(f"severity eq '{kwargs['severity']}'")
        if kwargs.get("category"):
            filters.append(f"category eq '{kwargs['category']}'")
        if kwargs.get("section_path"):
            # Use search.ismatch for prefix/contains matching on section_path
            escaped = kwargs['section_path'].replace("'", "''")
            filters.append(f"search.ismatch('{escaped}', 'section_path')")
        
        return " and ".join(filters)
    
    async def list_reports(
        self,
        customer_id: str,
        sid: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        latest_n: int = 10
    ) -> List[Document]:
        """List reports with filters."""
        client = self._get_client(self.docs_index)
        
        filter_str = self._build_filter(
            customer_id, sid=sid, date_from=date_from, date_to=date_to
        )
        
        results = client.search(
            search_text="*",
            filter=filter_str,
            order_by=["report_date desc"],
            top=latest_n
        )
        
        documents = []
        for r in results:
            doc = self._dict_to_document(r)
            documents.append(doc)
        
        return documents
    
    async def get_alerts(
        self,
        customer_id: str,
        doc_id: str,
        severity: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Alert]:
        """Get alerts for a document."""
        client = self._get_client(self.alerts_index)
        
        filter_str = self._build_filter(
            customer_id, doc_id=doc_id, severity=severity, category=category
        )
        
        results = client.search(
            search_text="*",
            filter=filter_str
        )
        
        alerts = []
        for r in results:
            alert = self._dict_to_alert(r)
            alerts.append(alert)
        
        return alerts
    
    async def get_alert(self, customer_id: str, doc_id: str, alert_id: str) -> Optional[Alert]:
        """Get single alert by ID."""
        client = self._get_client(self.alerts_index)
        
        filter_str = f"customer_id eq '{customer_id}' and doc_id eq '{doc_id}' and alert_id eq '{alert_id}'"
        
        results = client.search(
            search_text="*",
            filter=filter_str,
            top=1
        )
        
        for r in results:
            return self._dict_to_alert(r)
        
        return None
    
    async def get_chunks(
        self,
        customer_id: str,
        doc_id: Optional[str] = None,
        section_path: Optional[str] = None,
        chunk_ids: Optional[List[str]] = None,
        top_n: int = 20
    ) -> List[Chunk]:
        """Get chunks by filters or IDs."""
        client = self._get_client(self.chunks_index)
        
        if chunk_ids:
            # Fetch specific chunks
            filter_parts = [f"customer_id eq '{customer_id}'"]
            id_filter = " or ".join([f"chunk_id eq '{cid}'" for cid in chunk_ids])
            filter_parts.append(f"({id_filter})")
            filter_str = " and ".join(filter_parts)
        else:
            filter_str = self._build_filter(
                customer_id, doc_id=doc_id, section_path=section_path
            )
        
        results = client.search(
            search_text="*",
            filter=filter_str,
            top=top_n
        )
        
        chunks = []
        for r in results:
            chunk = self._dict_to_chunk(r)
            chunks.append(chunk)
        
        return chunks
    
    async def vector_search(
        self,
        customer_id: str,
        vector: List[float],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 12
    ) -> List[Chunk]:
        """Perform vector search with filters."""
        client = self._get_client(self.chunks_index)
        
        # Build filter — pass customer_id positionally, remaining filters as kwargs
        extra = filters or {}
        filter_str = self._build_filter(customer_id, **extra)
        
        # Vector query
        vector_query = VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=top_k,
            fields="content_vector"
        )
        
        results = client.search(
            search_text=None,
            vector_queries=[vector_query],
            filter=filter_str,
            top=top_k
        )
        
        chunks = []
        for r in results:
            chunk = self._dict_to_chunk(r)
            chunk.score = r.get('@search.score', 0)
            chunks.append(chunk)
        
        return chunks
    
    async def hybrid_search(
        self,
        customer_id: str,
        query: str,
        vector: List[float],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 12
    ) -> List[Chunk]:
        """Perform hybrid search (keyword + vector)."""
        client = self._get_client(self.chunks_index)
        
        # Build filter — pass customer_id positionally, remaining filters as kwargs
        extra = filters or {}
        filter_str = self._build_filter(customer_id, **extra)
        
        # Vector query
        vector_query = VectorizedQuery(
            vector=vector,
            k_nearest_neighbors=top_k,
            fields="content_vector"
        )
        
        # Hybrid search
        results = client.search(
            search_text=query,
            vector_queries=[vector_query],
            filter=filter_str,
            top=top_k,
            query_type=QueryType.SEMANTIC,
            semantic_configuration_name="ewa-semantic"
        )
        
        chunks = []
        for r in results:
            chunk = self._dict_to_chunk(r)
            chunk.score = r.get('@search.score', 0)
            chunk.reranker_score = r.get('@search.reranker_score')
            chunks.append(chunk)
        
        return chunks
    
    def _dict_to_document(self, d: Dict) -> Document:
        """Convert search result to Document."""
        return Document(
            doc_id=d.get("doc_id", ""),
            customer_id=d.get("customer_id", ""),
            sid=d.get("sid", ""),
            environment=d.get("environment"),
            report_date=self._parse_datetime(d.get("report_date")),
            analysis_from=self._parse_datetime(d.get("analysis_from")),
            analysis_to=self._parse_datetime(d.get("analysis_to")),
            title=d.get("title"),
            file_name=d.get("file_name", ""),
            pages=d.get("pages", 0),
            sha256=d.get("sha256", ""),
            source_url=d.get("source_url"),
            processing_status=d.get("processing_status", "unknown"),
            alert_count=d.get("alert_count")
        )
    
    def _dict_to_alert(self, d: Dict) -> Alert:
        """Convert search result to Alert."""
        return Alert(
            alert_id=d.get("alert_id", ""),
            customer_id=d.get("customer_id", ""),
            doc_id=d.get("doc_id", ""),
            sid=d.get("sid", ""),
            environment=d.get("environment"),
            report_date=self._parse_datetime(d.get("report_date")),
            title=d.get("title", ""),
            severity=Severity(d.get("severity", "unknown")),
            category=Category(d.get("category", "unknown")),
            section_path=d.get("section_path", ""),
            page_start=d.get("page_start", 1),
            page_end=d.get("page_end", 1),
            page_range=d.get("page_range", "1"),
            evidence_chunk_ids=d.get("evidence_chunk_ids", []),
            sap_note_ids=d.get("sap_note_ids", []),
            tags=d.get("tags", []),
            description=d.get("description"),
            recommendation=d.get("recommendation")
        )
    
    def _dict_to_chunk(self, d: Dict) -> Chunk:
        """Convert search result to Chunk."""
        severity = d.get("severity")
        category = d.get("category")
        
        return Chunk(
            chunk_id=d.get("chunk_id", ""),
            doc_id=d.get("doc_id", ""),
            customer_id=d.get("customer_id", ""),
            sid=d.get("sid", ""),
            environment=d.get("environment"),
            report_date=self._parse_datetime(d.get("report_date")),
            section_path=d.get("section_path", ""),
            page_start=d.get("page_start", 1),
            page_end=d.get("page_end", 1),
            severity=Severity(severity) if severity else None,
            category=Category(category) if category else None,
            sap_note_ids=d.get("sap_note_ids", []),
            content_md=d.get("content_md", ""),
            parent_chunk_id=d.get("parent_chunk_id"),
            header_level=d.get("header_level")
        )
    
    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from search result."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            return None

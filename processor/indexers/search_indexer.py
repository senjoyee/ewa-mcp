"""Azure AI Search indexer for documents, chunks, and alerts."""

from typing import List, Dict, Any
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient

from models.document import Document
from models.chunk import Chunk
from models.alert import Alert


class SearchIndexer:
    """Index documents, chunks, and alerts to Azure AI Search."""
    
    def __init__(self, endpoint: str, api_key: str):
        """Initialize indexer.
        
        Args:
            endpoint: Azure AI Search endpoint
            api_key: Azure AI Search admin API key
        """
        self.endpoint = endpoint
        self.credential = AzureKeyCredential(api_key)
        
        # Index names
        self.docs_index = "ewa-docs"
        self.chunks_index = "ewa-chunks"
        self.alerts_index = "ewa-alerts"
    
    def _get_search_client(self, index_name: str) -> SearchClient:
        """Get search client for index."""
        return SearchClient(
            endpoint=self.endpoint,
            index_name=index_name,
            credential=self.credential
        )
    
    def index_document(self, document: Document) -> bool:
        """Index document metadata.
        
        Args:
            document: Document model
            
        Returns:
            True if successful
        """
        client = self._get_search_client(self.docs_index)
        
        doc_dict = self._document_to_dict(document)
        
        try:
            client.upload_documents(documents=[doc_dict])
            return True
        except Exception as e:
            print(f"Error indexing document: {e}")
            return False
    
    def index_chunks(self, chunks: List[Chunk]) -> bool:
        """Index document chunks with vectors.
        
        Args:
            chunks: List of Chunk models
            
        Returns:
            True if successful
        """
        if not chunks:
            return True
        
        client = self._get_search_client(self.chunks_index)
        
        chunk_dicts = [self._chunk_to_dict(c) for c in chunks]
        
        try:
            # Upload in batches of 1000
            batch_size = 1000
            for i in range(0, len(chunk_dicts), batch_size):
                batch = chunk_dicts[i:i + batch_size]
                client.upload_documents(documents=batch)
            return True
        except Exception as e:
            print(f"Error indexing chunks: {e}")
            return False
    
    def index_alerts(self, alerts: List[Alert]) -> bool:
        """Index alerts.
        
        Args:
            alerts: List of Alert models
            
        Returns:
            True if successful
        """
        if not alerts:
            return True
        
        client = self._get_search_client(self.alerts_index)
        
        alert_dicts = [self._alert_to_dict(a) for a in alerts]
        
        try:
            client.upload_documents(documents=alert_dicts)
            return True
        except Exception as e:
            print(f"Error indexing alerts: {e}")
            return False
    
    def update_document_status(self, doc_id: str, status: str, alert_count: int = None) -> bool:
        """Update document processing status.
        
        Args:
            doc_id: Document ID
            status: New status
            alert_count: Optional alert count
        """
        client = self._get_search_client(self.docs_index)
        
        update = {
            "doc_id": doc_id,
            "processing_status": status
        }
        if alert_count is not None:
            update["alert_count"] = alert_count
        
        try:
            client.merge_documents(documents=[update])
            return True
        except Exception as e:
            print(f"Error updating document status: {e}")
            return False
    
    def _document_to_dict(self, doc: Document) -> Dict[str, Any]:
        """Convert Document model to search document dict."""
        return {
            "doc_id": doc.doc_id,
            "customer_id": doc.customer_id,
            "sid": doc.sid,
            "environment": doc.environment,
            "report_date": doc.report_date.isoformat() if doc.report_date else None,
            "analysis_from": doc.analysis_from.isoformat() if doc.analysis_from else None,
            "analysis_to": doc.analysis_to.isoformat() if doc.analysis_to else None,
            "title": doc.title,
            "file_name": doc.file_name,
            "pages": doc.pages,
            "sha256": doc.sha256,
            "source_url": doc.source_url,
            "processing_status": doc.processing_status,
            "alert_count": doc.alert_count
        }
    
    def _chunk_to_dict(self, chunk: Chunk) -> Dict[str, Any]:
        """Convert Chunk model to search document dict."""
        result = {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "customer_id": chunk.customer_id,
            "sid": chunk.sid,
            "environment": chunk.environment,
            "report_date": chunk.report_date.isoformat() if chunk.report_date else None,
            "section_path": chunk.section_path,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "severity": chunk.severity.value if chunk.severity else None,
            "category": chunk.category.value if chunk.category else None,
            "sap_note_ids": chunk.sap_note_ids,
            "content_md": chunk.content_md,
            "parent_chunk_id": chunk.parent_chunk_id,
            "header_level": chunk.header_level
        }
        
        # Add vector if present
        if chunk.content_vector:
            result["content_vector"] = chunk.content_vector
        
        return result
    
    def _alert_to_dict(self, alert: Alert) -> Dict[str, Any]:
        """Convert Alert model to search document dict."""
        return {
            "alert_id": alert.alert_id,
            "customer_id": alert.customer_id,
            "doc_id": alert.doc_id,
            "sid": alert.sid,
            "environment": alert.environment,
            "report_date": alert.report_date.isoformat() if alert.report_date else None,
            "title": alert.title,
            "severity": alert.severity.value,
            "category": alert.category.value,
            "section_path": alert.section_path,
            "page_start": alert.page_start,
            "page_end": alert.page_end,
            "page_range": alert.page_range,
            "evidence_chunk_ids": alert.evidence_chunk_ids,
            "sap_note_ids": alert.sap_note_ids,
            "tags": alert.tags,
            "description": alert.description,
            "recommendation": alert.recommendation
        }

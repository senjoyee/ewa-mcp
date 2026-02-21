"""Event Grid publisher for processing status events."""

import json
import uuid
from datetime import datetime
from typing import Optional

from azure.eventgrid import EventGridPublisherClient
from azure.core.credentials import AzureKeyCredential

from models.document import ProcessingEvent


class EventGridPublisher:
    """Publish processing status events to Event Grid."""
    
    def __init__(self, endpoint: str, api_key: str):
        """Initialize publisher.
        
        Args:
            endpoint: Event Grid topic endpoint
            api_key: Event Grid topic key
        """
        self.endpoint = endpoint
        self.credential = AzureKeyCredential(api_key)
        self.client = EventGridPublisherClient(
            endpoint=endpoint,
            credential=self.credential
        )
    
    def publish_event(
        self,
        event_type: str,
        customer_id: str,
        doc_id: str,
        sid: Optional[str],
        filename: str,
        stage: Optional[str] = None,
        error: Optional[str] = None
    ) -> bool:
        """Publish processing event.
        
        Args:
            event_type: Event type (EwaProcessingStarted/EwaProcessingCompleted/EwaProcessingFailed)
            customer_id: Customer tenant ID
            doc_id: Document ID
            sid: SAP System ID
            filename: Original filename
            stage: Processing stage
            error: Error message if failed
            
        Returns:
            True if successful
        """
        event = {
            "id": str(uuid.uuid4()),
            "eventType": event_type,
            "subject": f"/ewa/{customer_id}/{doc_id}",
            "eventTime": datetime.utcnow().isoformat(),
            "dataVersion": "1.0",
            "data": {
                "customer_id": customer_id,
                "doc_id": doc_id,
                "sid": sid,
                "filename": filename,
                "stage": stage,
                "error": error,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        try:
            self.client.send([event])
            return True
        except Exception as e:
            print(f"Error publishing event: {e}")
            return False
    
    def publish_started(self, customer_id: str, doc_id: str, sid: str, filename: str) -> bool:
        """Publish processing started event."""
        return self.publish_event(
            "EwaProcessingStarted",
            customer_id, doc_id, sid, filename,
            stage="extracting"
        )
    
    def publish_stage(
        self, 
        customer_id: str, 
        doc_id: str, 
        sid: str, 
        filename: str, 
        stage: str
    ) -> bool:
        """Publish stage update event."""
        return self.publish_event(
            "EwaProcessingStage",
            customer_id, doc_id, sid, filename,
            stage=stage
        )
    
    def publish_completed(
        self, 
        customer_id: str, 
        doc_id: str, 
        sid: str, 
        filename: str,
        alert_count: int = 0,
        chunk_count: int = 0
    ) -> bool:
        """Publish processing completed event."""
        return self.publish_event(
            "EwaProcessingCompleted",
            customer_id, doc_id, sid, filename,
            stage=f"completed (alerts: {alert_count}, chunks: {chunk_count})"
        )
    
    def publish_failed(
        self, 
        customer_id: str, 
        doc_id: str, 
        sid: str, 
        filename: str,
        error: str
    ) -> bool:
        """Publish processing failed event."""
        return self.publish_event(
            "EwaProcessingFailed",
            customer_id, doc_id, sid, filename,
            stage="failed",
            error=error
        )

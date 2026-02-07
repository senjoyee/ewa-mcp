"""GPT-5.2 Vision alert extraction from EWA priority tables."""

import base64
import json
from typing import List
from datetime import datetime
import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from shared.models.alert import Alert, AlertExtractionResult, Severity, Category


ALERT_EXTRACTION_PROMPT = """You are analyzing SAP EarlyWatch Alert priority table images. 
Extract ALL alerts visible in these images and return them as a JSON array.

For each alert, extract:
- title: The alert name/description (e.g., "Database Growth", "Security Patch Missing")
- severity: One of [very_high, high, medium, low, info] based on the priority section (Very High Priority = very_high, etc.)
- category: One of [security, performance, stability, configuration, lifecycle, data_volume, database, bw, other]
  - security: Security patches, vulnerabilities, audit issues
  - performance: Response time, throughput, resource utilization
  - stability: System crashes, dumps, errors
  - configuration: Parameter settings, profile recommendations
  - lifecycle: Support package levels, end-of-life notices
  - data_volume: Database size, table growth, archiving
  - database: DB-specific issues (Oracle, HANA, SQL Server)
  - bw: Business Warehouse specific
  - other: Anything not matching above
- sap_note_ids: Array of SAP note numbers mentioned (e.g., ["1234567", "2345678"])
- page_range: The page number where this alert appears (from image context)
- description: Full alert text/description if available
- recommendation: Recommended action if visible

Output format:
{
  "alerts": [
    {
      "title": "string",
      "severity": "very_high|high|medium|low|info",
      "category": "security|performance|stability|configuration|lifecycle|data_volume|database|bw|other",
      "sap_note_ids": ["1234567"],
      "page_range": "1",
      "description": "optional full text",
      "recommendation": "optional action"
    }
  ],
  "pages_processed": 4,
  "extraction_confidence": 0.95
}

Be thorough - extract every single alert visible in the priority tables."""


class VisionAlertExtractor:
    """Extract alerts from EWA priority tables using GPT-5.2 Vision."""
    
    def __init__(self, api_key: str, endpoint: str, deployment: str = "gpt-5.2"):
        """Initialize the vision extractor.
        
        Args:
            api_key: Azure OpenAI API key
            endpoint: Azure OpenAI endpoint
            deployment: Model deployment name (default: gpt-5.2)
        """
        self.client = openai.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2024-12-01-preview"
        )
        self.deployment = deployment
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def extract_alerts(
        self, 
        image_bytes_list: List[bytes], 
        customer_id: str, 
        doc_id: str, 
        sid: str,
        environment: str = None
    ) -> AlertExtractionResult:
        """Extract alerts from priority page images.
        
        Args:
            image_bytes_list: List of PNG image bytes for pages 1-4
            customer_id: Customer tenant ID
            doc_id: Document ID
            sid: SAP System ID
            environment: System environment
            
        Returns:
            AlertExtractionResult with extracted alerts
        """
        # Build content array with images
        content = [{"type": "text", "text": ALERT_EXTRACTION_PROMPT}]
        
        for img_bytes in image_bytes_list:
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}",
                    "detail": "high"
                }
            })
        
        # Call GPT-5.2 Vision
        response = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
            max_tokens=4096,
            temperature=0.0  # Deterministic extraction
        )
        
        # Parse response
        result_text = response.choices[0].message.content
        result_json = json.loads(result_text)
        
        # Convert to Alert models
        alerts = []
        for alert_data in result_json.get("alerts", []):
            alert = Alert(
                alert_id=f"{doc_id}_{len(alerts)}",
                customer_id=customer_id,
                doc_id=doc_id,
                sid=sid,
                environment=environment,
                title=alert_data.get("title", "Unknown Alert"),
                severity=Severity(alert_data.get("severity", "unknown")),
                category=Category(alert_data.get("category", "unknown")),
                section_path=f"Priority/{alert_data.get('severity', 'unknown').replace('_', ' ').title()}",
                page_start=int(alert_data.get("page_range", "1")),
                page_end=int(alert_data.get("page_range", "1")),
                page_range=alert_data.get("page_range", "1"),
                sap_note_ids=alert_data.get("sap_note_ids", []),
                description=alert_data.get("description"),
                recommendation=alert_data.get("recommendation")
            )
            alerts.append(alert)
        
        return AlertExtractionResult(
            alerts=alerts,
            pages_processed=result_json.get("pages_processed", len(image_bytes_list)),
            extraction_confidence=result_json.get("extraction_confidence")
        )

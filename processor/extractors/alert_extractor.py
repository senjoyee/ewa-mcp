"""GPT-5.2 Vision alert extraction from EWA priority tables via Azure AI Foundry."""

import base64
import json
import logging
import re
from typing import Any, Dict, List
from datetime import datetime
import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from models.alert import Alert, AlertExtractionResult, Severity, Category


logger = logging.getLogger(__name__)


def _parse_result_json(result_text: str) -> dict:
    """Parse model output that may include markdown fences or explanatory text."""
    text = (result_text or "").strip()
    if not text:
        raise ValueError("Empty model response")

    # Common case: ```json { ... } ```
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    # Fallback: parse first top-level JSON object if extra prose exists.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    # Final attempt: raw content is JSON.
    return json.loads(text)


def _extract_text_from_response_output(output_items: Any) -> str:
    """Extract text content from Responses API output blocks."""
    if not output_items:
        return ""

    chunks: List[str] = []
    for item in output_items:
        if isinstance(item, dict):
            content = item.get("content") or []
        else:
            content = getattr(item, "content", None) or []

        if isinstance(content, str):
            chunks.append(content)
            continue

        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                text_value = part.get("text")
            else:
                part_type = getattr(part, "type", None)
                text_value = getattr(part, "text", None)

            if isinstance(text_value, dict):
                text_value = text_value.get("value") or text_value.get("text")

            if part_type in {"output_text", "text"} and text_value:
                chunks.append(text_value)

    return "\n".join(chunks)


def _parse_page_bounds(page_range: str, default_page: int) -> tuple[int, int]:
    """Parse a page range string like '3' or '3-4' into start/end ints."""
    text = str(page_range or "").strip()
    if not text:
        return default_page, default_page

    match = re.match(r"^(\d+)\s*(?:-\s*(\d+))?$", text)
    if not match:
        return default_page, default_page

    start = int(match.group(1))
    end = int(match.group(2) or start)
    return start, end


ALERT_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "alerts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["very_high", "high", "medium", "low", "info", "unknown"],
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "security",
                            "performance",
                            "stability",
                            "configuration",
                            "lifecycle",
                            "data_volume",
                            "database",
                            "bw",
                            "other",
                            "unknown",
                        ],
                    },
                    "sap_note_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "page_range": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "recommendation": {"type": ["string", "null"]},
                },
                "required": [
                    "title",
                    "severity",
                    "category",
                    "sap_note_ids",
                    "page_range",
                    "description",
                    "recommendation",
                ],
                "additionalProperties": False,
            },
        },
        "pages_processed": {"type": "integer"},
        "extraction_confidence": {"type": "number"},
    },
    "required": ["alerts", "pages_processed", "extraction_confidence"],
    "additionalProperties": False,
}


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
    """Extract alerts from EWA priority tables using GPT-5.2 via Azure AI Foundry."""
    
    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str = "gpt-5.2",
        request_timeout_seconds: int = 180,
    ):
        """Initialize the vision extractor.
        
        Args:
            api_key: Azure AI Foundry API key
            endpoint: Azure AI Foundry endpoint (e.g., https://<project>.<region>.models.ai.azure.com)
            deployment: Model deployment name (default: gpt-5.2)
        """
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url=endpoint.rstrip("/") + "/",
            timeout=request_timeout_seconds,
        )
        self.deployment = deployment
        self.request_timeout_seconds = request_timeout_seconds
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=4))
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
        # Build content array with images for Responses API
        content = [{"type": "input_text", "text": ALERT_EXTRACTION_PROMPT}]

        for idx, img_bytes in enumerate(image_bytes_list, start=1):
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            content.append({"type": "input_image", "image_url": f"data:image/png;base64,{base64_image}"})
            content.append({"type": "input_text", "text": f"[Page {idx}]"})

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "extract_ewa_alerts",
                "schema": ALERT_EXTRACTION_SCHEMA,
                "strict": True,
            },
        }
        text_format = {
            "format": {
                "type": "json_schema",
                "name": "extract_ewa_alerts",
                "schema": ALERT_EXTRACTION_SCHEMA,
                "strict": True,
            }
        }

        try:
            response = self.client.responses.create(
                model=self.deployment,
                input=[{"role": "user", "content": content}],
                response_format=response_format,
                reasoning={"effort": "none"},
                max_output_tokens=4096,
                timeout=self.request_timeout_seconds,
            )
        except TypeError:
            response = self.client.responses.create(
                model=self.deployment,
                input=[{"role": "user", "content": content}],
                text=text_format,
                reasoning={"effort": "none"},
                max_output_tokens=4096,
                timeout=self.request_timeout_seconds,
            )

        result_json: Dict[str, Any] = {}
        parsed = getattr(response, "output_parsed", None)
        if parsed is not None:
            if hasattr(parsed, "model_dump"):
                result_json = parsed.model_dump()
            elif isinstance(parsed, dict):
                result_json = parsed
            elif isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
                result_json = parsed[0]

        if not result_json:
            result_text = getattr(response, "output_text", None) or _extract_text_from_response_output(
                getattr(response, "output", None)
            )
            result_json = _parse_result_json(result_text)
        
        # Convert to Alert models
        alerts = []
        for idx, alert_data in enumerate(result_json.get("alerts", [])):
            page_start, page_end = _parse_page_bounds(alert_data.get("page_range", "1"), default_page=1)
            alert = Alert(
                alert_id=f"{doc_id}_{idx}",
                customer_id=customer_id,
                doc_id=doc_id,
                sid=sid,
                environment=environment,
                title=alert_data.get("title", "Unknown Alert"),
                severity=Severity(alert_data.get("severity", "unknown")),
                category=Category(alert_data.get("category", "unknown")),
                section_path=f"Priority/{alert_data.get('severity', 'unknown').replace('_', ' ').title()}",
                page_start=page_start,
                page_end=page_end,
                page_range=alert_data.get("page_range", "1"),
                sap_note_ids=alert_data.get("sap_note_ids", []),
                description=alert_data.get("description"),
                recommendation=alert_data.get("recommendation")
            )
            alerts.append(alert)

        logger.info("Vision extraction produced %d alerts", len(alerts))
        
        return AlertExtractionResult(
            alerts=alerts,
            pages_processed=result_json.get("pages_processed", len(image_bytes_list)),
            extraction_confidence=result_json.get("extraction_confidence")
        )

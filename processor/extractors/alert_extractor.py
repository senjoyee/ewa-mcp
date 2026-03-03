"""GPT-5.2 Vision check overview extraction from EWA summary tables."""

import base64
import json
import logging
import re
from typing import Any, Dict, List
import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from models.alert import CheckOverviewRow, CheckOverviewExtractionResult


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


CHECK_OVERVIEW_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "row_type": {
                        "type": "string",
                        "enum": ["topic", "subtopic"],
                    },
                    "topic_name": {"type": "string"},
                    "subtopic_name": {"type": ["string", "null"]},
                    "topic_rating_raw": {"type": ["string", "null"]},
                    "subtopic_rating_raw": {"type": ["string", "null"]},
                    "topic_rating_normalized": {
                        "type": ["string", "null"],
                        "enum": ["red", "yellow", "green", "grey", "unknown", None],
                    },
                    "subtopic_rating_normalized": {
                        "type": ["string", "null"],
                        "enum": ["red", "yellow", "green", "grey", "unknown", None],
                    },
                    "reference_page": {"type": ["string", "null"], "description": "Page number pointing to the detailed evidence/section"},
                    "reference_section": {"type": ["string", "null"], "description": "Section number (e.g., 3.1.2) if present in the table"},
                    "source_page": {"type": ["integer", "null"]},
                },
                "required": [
                    "row_type",
                    "topic_name",
                    "subtopic_name",
                    "topic_rating_raw",
                    "subtopic_rating_raw",
                    "topic_rating_normalized",
                    "subtopic_rating_normalized",
                    "reference_page",
                    "reference_section",
                    "source_page",
                ],
                "additionalProperties": False,
            },
        },
        "pages_processed": {"type": "integer"},
        "extraction_confidence": {"type": "number"},
    },
    "required": ["checks", "pages_processed", "extraction_confidence"],
    "additionalProperties": False,
}


CHECK_OVERVIEW_EXTRACTION_PROMPT = """You are analyzing SAP EarlyWatch Alert Check Overview table images.
Extract EVERY visible row from the check overview table and return JSON.

Use this row mapping:
- row_type: "topic" when Topic column has a value and Subtopic is blank/group; "subtopic" for concrete checks under a topic.
- topic_name: value in Topic column.
- subtopic_name: value in Subtopic column when present.
- topic_rating_raw / subtopic_rating_raw: raw visible icon/text marker in corresponding rating column.
- topic_rating_normalized / subtopic_rating_normalized: normalize to red|yellow|green|grey|unknown.
- reference_page: page reference in the row pointing to detailed evidence (if visible).
- reference_section: section reference like 3.1.2 if visible.
- source_page: page number of the image where this row is read.

Do not infer missing values; use null/unknown where appropriate.
Output all rows in reading order."""


class VisionAlertExtractor:
    """Extract check overview rows from EWA summary tables via Azure AI Foundry."""
    
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
        # Hard lock to gpt-5.2 for vision extraction.
        self.deployment = "gpt-5.2"
        self.request_timeout_seconds = request_timeout_seconds
    
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=4))
    def extract_alerts(
        self, 
        image_bytes_list: List[bytes], 
        customer_id: str, 
        doc_id: str, 
        sid: str
    ) -> CheckOverviewExtractionResult:
        """Extract check overview rows from summary page images.
        
        Args:
            image_bytes_list: List of PNG image bytes for pages 1-4
            customer_id: Customer tenant ID
            doc_id: Document ID
            sid: SAP System ID
            
        Returns:
            CheckOverviewExtractionResult with extracted check-overview rows
        """
        # Build content array for Responses API
        content = [{"type": "input_text", "text": CHECK_OVERVIEW_EXTRACTION_PROMPT}]

        for idx, img_bytes in enumerate(image_bytes_list, start=1):
            base64_image = base64.b64encode(img_bytes).decode('utf-8')
            content.append({
                "type": "input_image",
                "image_url": f"data:image/png;base64,{base64_image}",
            })
            content.append({"type": "input_text", "text": f"[Page {idx}]"})

        text_format = {
            "type": "json_schema",
            "name": "extract_ewa_check_overview",
            "schema": CHECK_OVERVIEW_EXTRACTION_SCHEMA,
            "strict": True,
        }

        try:
            response = self.client.responses.create(
                model=self.deployment,
                input=[{"role": "user", "content": content}],
                reasoning={"effort": "high"},
                text={"format": text_format},
                max_output_tokens=16384,
                timeout=self.request_timeout_seconds,
            )
        except openai.BadRequestError as exc:
            # If structured outputs fail explicitly, fall back to plain text output mode.
            logger.warning("Structured outputs failing on Responses API, trying plain text: %s", exc)
            response = self.client.responses.create(
                model=self.deployment,
                input=[{"role": "user", "content": content}],
                reasoning={"effort": "high"},
                max_output_tokens=16384,
                timeout=self.request_timeout_seconds,
            )

        result_json: Dict[str, Any] = {}
        raw_text = getattr(response, "output_text", None) or _extract_text_from_response_output(getattr(response, "output", None))

        if raw_text:
            try:
                result_json = _parse_result_json(raw_text)
            except ValueError as e:
                logger.error("Failed to parse JSON from model output: %s", e)
                logger.error("Raw text was: %s", repr(raw_text))
                result_json = {"checks": [], "pages_processed": len(image_bytes_list), "extraction_confidence": 0.0}
        
        # Convert to CheckOverviewRow models
        checks = []
        current_topic_name = "unknown"
        current_topic_rating_raw = None
        current_topic_rating_normalized = None

        for idx, check_data in enumerate(result_json.get("checks", [])):
            ref_page = check_data.get("reference_page") or "1"
            page_start, page_end = _parse_page_bounds(ref_page, default_page=1)

            row_type = check_data.get("row_type", "subtopic")
            extracted_topic = check_data.get("topic_name")

            # Update topic context if it's a new topic or explicitly stated
            is_valid_topic = extracted_topic and extracted_topic.strip() and extracted_topic.lower() != "unknown"
            if row_type == "topic" and is_valid_topic:
                current_topic_name = extracted_topic
                current_topic_rating_raw = check_data.get("topic_rating_raw")
                current_topic_rating_normalized = check_data.get("topic_rating_normalized")
            elif is_valid_topic:
                current_topic_name = extracted_topic
                if check_data.get("topic_rating_raw"):
                    current_topic_rating_raw = check_data.get("topic_rating_raw")
                if check_data.get("topic_rating_normalized"):
                    current_topic_rating_normalized = check_data.get("topic_rating_normalized")

            # Forward fill values for subtopics
            final_topic_name = current_topic_name
            final_topic_rating_raw = check_data.get("topic_rating_raw") or current_topic_rating_raw
            final_topic_rating_normalized = check_data.get("topic_rating_normalized") or current_topic_rating_normalized

            effective_rating = check_data.get("subtopic_rating_normalized") or final_topic_rating_normalized
            severity = "unknown"
            if effective_rating == "red":
                severity = "high"
            elif effective_rating == "yellow":
                severity = "medium"
            elif effective_rating == "green":
                severity = "ok"
            elif effective_rating == "grey":
                severity = "info"

            check = CheckOverviewRow(
                check_id=f"{doc_id}_check_{idx:04d}",
                customer_id=customer_id,
                doc_id=doc_id,
                sid=sid,
                row_type=row_type,
                topic_name=final_topic_name,
                subtopic_name=check_data.get("subtopic_name"),
                topic_rating_raw=final_topic_rating_raw,
                subtopic_rating_raw=check_data.get("subtopic_rating_raw"),
                topic_rating_normalized=final_topic_rating_normalized,
                subtopic_rating_normalized=check_data.get("subtopic_rating_normalized"),
                severity=severity,
                reference_page=check_data.get("reference_page"),
                reference_section=check_data.get("reference_section"),
                page_start=page_start,
                page_end=page_end,
                page_range=ref_page,
                source_page=check_data.get("source_page")
            )
            checks.append(check)

        logger.info("Vision extraction produced %d check overview rows", len(checks))
        
        return CheckOverviewExtractionResult(
            checks=checks,
            pages_processed=result_json.get("pages_processed", len(image_bytes_list)),
            extraction_confidence=result_json.get("extraction_confidence")
        )

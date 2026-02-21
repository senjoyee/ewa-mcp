"""Run alert extraction as a standalone local script.

Usage:
  python scripts/run_alert_extraction_standalone.py --pdf ..\tmp-smoke.pdf
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROCESSOR_DIR = Path(__file__).resolve().parents[1]
if str(PROCESSOR_DIR) not in sys.path:
    sys.path.insert(0, str(PROCESSOR_DIR))

from extractors.alert_extractor import VisionAlertExtractor
from extractors.pdf_extractor import PDFExtractor


def load_local_settings(settings_path: Path) -> None:
    """Load processor/local.settings.json Values into process environment if missing."""
    if not settings_path.exists():
        return

    data = json.loads(settings_path.read_text(encoding="utf-8"))
    values = data.get("Values", {})
    for key, value in values.items():
        if key not in os.environ:
            os.environ[key] = str(value)


def save_priority_page_images(image_bytes_list: list[bytes], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, image_bytes in enumerate(image_bytes_list, start=1):
        out_file = out_dir / f"page_{idx}.png"
        out_file.write_bytes(image_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run standalone Vision alert extraction for pages 1-4")
    parser.add_argument("--pdf", required=True, help="Absolute or relative path to PDF")
    parser.add_argument("--customer-id", default="local-test", help="Customer ID used in alert model")
    parser.add_argument("--save-images-dir", default="tmp_alert_pages", help="Directory to write rendered pages 1-4")
    parser.add_argument("--deployment", default=None, help="Override model deployment (default from env or gpt-5.2)")
    args = parser.parse_args()

    processor_dir = Path(__file__).resolve().parents[1]
    load_local_settings(processor_dir / "local.settings.json")

    api_key = os.environ.get("AZURE_AI_FOUNDRY_API_KEY")
    endpoint = os.environ.get("AZURE_AI_FOUNDRY_ENDPOINT")
    deployment = args.deployment or os.environ.get("AZURE_AI_VISION_DEPLOYMENT", "gpt-5.2")

    if not api_key or not endpoint:
        raise RuntimeError("Missing AZURE_AI_FOUNDRY_API_KEY or AZURE_AI_FOUNDRY_ENDPOINT")

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pdf_extractor = PDFExtractor()
    alert_extractor = VisionAlertExtractor(
        api_key=api_key,
        endpoint=endpoint,
        deployment=deployment,
    )

    pdf_bytes = pdf_path.read_bytes()
    document, _markdown, priority_images = pdf_extractor.extract(
        pdf_bytes=pdf_bytes,
        customer_id=args.customer_id,
        file_name=pdf_path.name,
    )

    save_dir = Path(args.save_images_dir).resolve()
    save_priority_page_images(priority_images, save_dir)

    result = alert_extractor.extract_alerts(
        image_bytes_list=priority_images,
        customer_id=args.customer_id,
        doc_id=document.doc_id,
        sid=document.sid,
        environment=document.environment,
    )

    output = {
        "pdf": str(pdf_path),
        "pages_rendered": len(priority_images),
        "render_output_dir": str(save_dir),
        "deployment": deployment,
        "alerts_count": len(result.alerts),
        "pages_processed": result.pages_processed,
        "extraction_confidence": result.extraction_confidence,
        "alerts": [a.model_dump(mode="json") for a in result.alerts],
    }
    print(json.dumps(output, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

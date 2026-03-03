import logging
import json
from processor.extractors.alert_extractor import VisionAlertExtractor

logging.basicConfig(level=logging.INFO)

with open(r"c:\GenAI\ewa-mcp\processor\local.settings.json") as f:
    settings = json.load(f)["Values"]

try:
    extractor = VisionAlertExtractor(
        api_key=settings["AZURE_OPENAI_API_KEY"],
        endpoint=settings["AZURE_OPENAI_ENDPOINT"],
        deployment=settings["AZURE_OPENAI_VISION_DEPLOYMENT"]
    )
    
    images = []
    for i in range(1, 5):
        path = f"c:/GenAI/ewa-mcp/processor/tmp_alert_pages/page_{i}.png"
        with open(path, "rb") as f:
            images.append(f.read())
            
    print("Running vision extractor...")
    result = extractor.extract_alerts(images, "cust1", "doc1", "sid1", "prod")
    print("Success. Extracted", len(result.checks), "checks.")
    for c in result.checks:
        print(c.topic_name, "-", c.subtopic_name)
except Exception as e:
    logging.exception("Failed")

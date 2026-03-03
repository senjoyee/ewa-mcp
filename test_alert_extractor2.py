import logging
import json
from processor.extractors.alert_extractor import VisionAlertExtractor, _extract_text_from_response_output

logging.basicConfig(level=logging.INFO)

with open(r"c:\GenAI\ewa-mcp\processor\local.settings.json") as f:
    settings = json.load(f)["Values"]

try:
    extractor = VisionAlertExtractor(
        api_key=settings["AZURE_AI_FOUNDRY_API_KEY"],
        endpoint=settings["AZURE_AI_FOUNDRY_ENDPOINT"],
        deployment=settings["AZURE_AI_VISION_DEPLOYMENT"]
    )
    
    images = []
    for i in range(1, 5):
        path = f"c:/GenAI/ewa-mcp/processor/tmp_alert_pages/page_{i}.png"
        with open(path, "rb") as f:
            images.append(f.read())
            
    print("Running vision extractor...")
    
    # manual invoke to see output
    import base64
    content = [{"type": "input_text", "text": "Extract all check overview rows"}]
    for idx, img_bytes in enumerate(images, start=1):
        base64_image = base64.b64encode(img_bytes).decode('utf-8')
        content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{base64_image}",
        })
        content.append({"type": "input_text", "text": f"[Page {idx}]"})

    response = extractor.client.responses.create(
        model=extractor.deployment,
        input=[{"role": "user", "content": content}],
        reasoning={"effort": "high"},
        max_output_tokens=4096,
        timeout=180,
    )
    raw_text = getattr(response, "output_text", None) or _extract_text_from_response_output(getattr(response, "output", None))
    print("RAW TEXT LENGTH:", len(raw_text))
    print("RAW TEXT SNIPPET:", repr(raw_text[-200:]))
    
except Exception as e:
    logging.exception("Failed")

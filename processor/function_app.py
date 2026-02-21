"""Azure Function entry point for EWA PDF processing.

Trigger: Event Grid HTTP webhook (Microsoft.Storage.BlobCreated)

The function is exposed as an HTTP endpoint so that Azure Event Grid
can push events to it.  It handles two request types:

1. SubscriptionValidationEvent  (one-time handshake when the Event 
   Subscription is first created — must return the validationCode).
2. Microsoft.Storage.BlobCreated  (the real trigger — downloads the
   blob and runs the full processing pipeline).
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import azure.functions as func
from azure.storage.blob import BlobServiceClient

from extractors.pdf_extractor import PDFExtractor
from extractors.alert_extractor import VisionAlertExtractor
from chunkers.markdown_chunker import MarkdownChunker
from embedders.openai_embedder import OpenAIEmbedder
from indexers.search_indexer import SearchIndexer
from eventgrid.publisher import EventGridPublisher


app = func.FunctionApp()


def _parse_blob_path(blob_url: str) -> tuple[str, str, str]:
    """Extract container, customer_id, and filename from a blob URL.

    Blob URL format:
      https://<account>.blob.core.windows.net/<container>/<customer_id>/<filename>

    Returns:
        (container_name, customer_id, file_name)
    """
    # Strip scheme and host to get /<container>/<customer_id>/<filename>
    path = blob_url.split(".blob.core.windows.net", 1)[-1]
    parts = [p for p in path.split("/") if p]

    if len(parts) < 3:
        raise ValueError(f"Unexpected blob URL format: {blob_url}")

    container_name = parts[0]
    customer_id = parts[1]
    file_name = "/".join(parts[2:])  # handles nested paths
    return container_name, customer_id, file_name


@app.route(route="ProcessEwaBlob", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def process_ewa_blob(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP-triggered handler for Event Grid BlobCreated events.

    Azure Event Grid delivers events as a JSON array.  Each item in
    the array has an 'eventType' field:

    - Microsoft.EventGrid.SubscriptionValidationEvent
        → return {'validationResponse': <code>}
    - Microsoft.Storage.BlobCreated
        → download & process the blob
    """
    try:
        body = req.get_json()
    except ValueError as exc:
        logging.error("Could not parse request body as JSON: %s", exc)
        return func.HttpResponse("Bad request – body is not JSON", status_code=400)

    # Event Grid sends a *list* of events
    events = body if isinstance(body, list) else [body]

    for event in events:
        event_type = event.get("eventType", "")

        # ── Validation handshake ────────────────────────────────────────────
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            validation_code = event["data"]["validationCode"]
            logging.info("Event Grid subscription validation: %s", validation_code)
            return func.HttpResponse(
                json.dumps({"validationResponse": validation_code}),
                status_code=200,
                mimetype="application/json",
            )

        # ── Blob created ────────────────────────────────────────────────────
        if event_type == "Microsoft.Storage.BlobCreated":
            blob_url = event["data"]["url"]
            logging.info("BlobCreated event received for: %s", blob_url)

            try:
                container_name, customer_id, file_name = _parse_blob_path(blob_url)
            except ValueError as exc:
                logging.error("Cannot parse blob path: %s", exc)
                return func.HttpResponse(str(exc), status_code=400)

            # Only process PDFs
            if not file_name.lower().endswith(".pdf"):
                logging.info("Skipping non-PDF blob: %s", file_name)
                return func.HttpResponse("Skipped – not a PDF", status_code=200)

            _run_pipeline(customer_id, file_name, blob_url)
            return func.HttpResponse("OK", status_code=200)

        logging.warning("Unhandled event type: %s", event_type)

    return func.HttpResponse("OK", status_code=200)


def _run_pipeline(customer_id: str, file_name: str, blob_url: str) -> None:
    """Download blob and run the full EWA processing pipeline."""

    # ── Download blob bytes ─────────────────────────────────────────────────
    blob_connection_string = os.environ["BLOB_CONNECTION_STRING"]
    blob_service_client = BlobServiceClient.from_connection_string(blob_connection_string)

    # Derive container from URL (always ewa-uploads in practice)
    container_name, _, _ = _parse_blob_path(blob_url)
    blob_path = f"{customer_id}/{file_name}"

    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=blob_path
    )
    pdf_bytes = blob_client.download_blob().readall()
    logging.info("Downloaded %d bytes for %s/%s", len(pdf_bytes), customer_id, file_name)

    # ── Initialise pipeline components ─────────────────────────────────────
    # SearchIndexer is created first so it is available in the except handler
    indexer = SearchIndexer(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        api_key=os.environ["AZURE_SEARCH_API_KEY"],
    )

    event_publisher = None
    doc_id = None
    sid = None

    try:
        pdf_extractor = PDFExtractor()
        alert_extractor = VisionAlertExtractor(
            api_key=os.environ["AZURE_AI_FOUNDRY_API_KEY"],
            endpoint=os.environ["AZURE_AI_FOUNDRY_ENDPOINT"],
            deployment=os.environ.get("AZURE_AI_VISION_DEPLOYMENT", "gpt-5.2"),
        )
        chunker = MarkdownChunker(max_chunk_size=4000)
        embedder = OpenAIEmbedder(
            api_key=os.environ["AZURE_AI_FOUNDRY_API_KEY"],
            endpoint=os.environ["AZURE_AI_FOUNDRY_ENDPOINT"],
            deployment=os.environ.get("AZURE_AI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
        )

        # Event Grid publisher is optional
        try:
            event_publisher = EventGridPublisher(
                endpoint=os.environ["EVENTGRID_ENDPOINT"],
                api_key=os.environ["EVENTGRID_KEY"],
            )
        except Exception as exc:
            logging.warning("Event Grid publisher disabled: %s", exc)

        # Step 1: Extract PDF content
        logging.info("Step 1: Extracting PDF content from %s...", file_name)
        document, markdown_text, priority_images = pdf_extractor.extract(
            pdf_bytes, customer_id, file_name
        )

        doc_id = document.doc_id
        sid = document.sid

        if event_publisher:
            event_publisher.publish_started(customer_id, doc_id, sid, file_name)

        indexer.index_document(document)

        # Step 2: Extract alerts with Vision AI
        logging.info("Step 2: Extracting alerts with Vision AI...")
        if event_publisher:
            event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "alert_extraction")

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    alert_extractor.extract_alerts,
                    priority_images,
                    customer_id,
                    doc_id,
                    sid,
                    document.environment,
                )
                alert_result = future.result(timeout=90)

            alerts = alert_result.alerts
            logging.info("Extracted %d alerts", len(alerts))
        except FuturesTimeoutError:
            logging.error("Alert extraction timed out after 90s; continuing without alerts")
            alerts = []
        except Exception as exc:
            logging.exception("Alert extraction failed, continuing without alerts: %s", exc)
            alerts = []

        # Step 3: Chunk markdown
        logging.info("Step 3: Chunking markdown...")
        if event_publisher:
            event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "chunking")

        chunks = chunker.chunk_document(
            markdown=markdown_text,
            doc_id=doc_id,
            customer_id=customer_id,
            sid=sid,
            environment=document.environment,
            report_date=document.report_date,
        )
        logging.info("Created %d chunks", len(chunks))

        # Step 4: Link alerts to evidence chunks
        logging.info("Step 4: Linking alerts to evidence chunks...")
        alerts = chunker.link_alerts_to_chunks(alerts, chunks)

        # Step 5: Generate embeddings
        logging.info("Step 5: Generating embeddings...")
        if event_publisher:
            event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "embedding")

        chunk_texts = [c.content_md for c in chunks]
        embeddings = embedder.embed_batch(chunk_texts)
        for chunk, embedding in zip(chunks, embeddings):
            chunk.content_vector = embedding

        # Step 6: Index to Azure AI Search
        logging.info("Step 6: Indexing to Azure AI Search...")
        if event_publisher:
            event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "indexing")

        indexer.index_chunks(chunks)
        indexer.index_alerts(alerts)
        indexer.update_document_status(doc_id, "completed", len(alerts))

        if event_publisher:
            event_publisher.publish_completed(
                customer_id, doc_id, sid, file_name,
                alert_count=len(alerts),
                chunk_count=len(chunks),
            )

        logging.info(
            "Successfully processed %s: %d alerts, %d chunks",
            file_name, len(alerts), len(chunks),
        )

    except Exception as exc:
        error_msg = str(exc)
        logging.error("Error processing %s: %s", file_name, error_msg)

        if doc_id:
            indexer.update_document_status(doc_id, "failed")
            if event_publisher:
                event_publisher.publish_failed(customer_id, doc_id, sid, file_name, error_msg)

        raise

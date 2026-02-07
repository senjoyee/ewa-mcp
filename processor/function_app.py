"""Azure Function entry point for EWA PDF processing."""

import logging
import os
import uuid
from datetime import datetime

import azure.functions as func
from azure.storage.blob import BlobServiceClient

from processor.extractors.pdf_extractor import PDFExtractor
from processor.extractors.alert_extractor import VisionAlertExtractor
from processor.chunkers.markdown_chunker import MarkdownChunker
from processor.embedders.openai_embedder import OpenAIEmbedder
from processor.indexers.search_indexer import SearchIndexer
from processor.eventgrid.publisher import EventGridPublisher


def main(myblob: func.InputStream):
    """Process uploaded EWA PDF.
    
    Triggered by blob upload to ewa-uploads/{customer_id}/{filename}
    """
    logging.info(f"Python blob trigger function processing blob: {myblob.name}")
    
    # Parse blob path to get customer_id and filename
    blob_path = myblob.name
    path_parts = blob_path.split('/')
    
    if len(path_parts) < 2:
        logging.error(f"Invalid blob path format: {blob_path}")
        return
    
    customer_id = path_parts[0] if path_parts[0] else "unknown"
    file_name = path_parts[-1] if path_parts[-1] else "unknown.pdf"
    
    # Initialize components
    pdf_extractor = PDFExtractor()
    alert_extractor = VisionAlertExtractor(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        deployment=os.environ.get("AZURE_OPENAI_VISION_DEPLOYMENT", "gpt-5.2")
    )
    chunker = MarkdownChunker(max_chunk_size=4000)
    embedder = OpenAIEmbedder(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        deployment=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    )
    indexer = SearchIndexer(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        api_key=os.environ["AZURE_SEARCH_API_KEY"]
    )
    event_publisher = EventGridPublisher(
        endpoint=os.environ["EVENTGRID_ENDPOINT"],
        api_key=os.environ["EVENTGRID_KEY"]
    )
    
    doc_id = None
    sid = None
    
    try:
        # Step 1: Extract PDF content
        logging.info("Step 1: Extracting PDF content...")
        pdf_bytes = myblob.read()
        
        document, markdown_text, priority_images = pdf_extractor.extract(
            pdf_bytes, customer_id, file_name
        )
        
        doc_id = document.doc_id
        sid = document.sid
        
        # Publish started event
        event_publisher.publish_started(customer_id, doc_id, sid, file_name)
        
        # Index document metadata
        indexer.index_document(document)
        
        # Step 2: Extract alerts using GPT-5.2 Vision
        logging.info("Step 2: Extracting alerts with GPT-5.2 Vision...")
        event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "alert_extraction")
        
        alert_result = alert_extractor.extract_alerts(
            priority_images, customer_id, doc_id, sid, document.environment
        )
        
        alerts = alert_result.alerts
        logging.info(f"Extracted {len(alerts)} alerts")
        
        # Step 3: Chunk markdown content
        logging.info("Step 3: Chunking markdown content...")
        event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "chunking")
        
        chunks = chunker.chunk_document(
            markdown=markdown_text,
            doc_id=doc_id,
            customer_id=customer_id,
            sid=sid,
            environment=document.environment,
            report_date=document.report_date
        )
        
        logging.info(f"Created {len(chunks)} chunks")
        
        # Step 4: Link alerts to chunks
        logging.info("Step 4: Linking alerts to evidence chunks...")
        alerts = chunker.link_alerts_to_chunks(alerts, chunks)
        
        # Step 5: Generate embeddings
        logging.info("Step 5: Generating embeddings...")
        event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "embedding")
        
        chunk_texts = [c.content_md for c in chunks]
        embeddings = embedder.embed_batch(chunk_texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.content_vector = embedding
        
        # Step 6: Index to Azure AI Search
        logging.info("Step 6: Indexing to Azure AI Search...")
        event_publisher.publish_stage(customer_id, doc_id, sid, file_name, "indexing")
        
        indexer.index_chunks(chunks)
        indexer.index_alerts(alerts)
        indexer.update_document_status(doc_id, "completed", len(alerts))
        
        # Publish completed event
        event_publisher.publish_completed(
            customer_id, doc_id, sid, file_name, 
            alert_count=len(alerts), 
            chunk_count=len(chunks)
        )
        
        logging.info(f"Successfully processed {file_name}: {len(alerts)} alerts, {len(chunks)} chunks")
        
    except Exception as e:
        error_msg = str(e)
        logging.error(f"Error processing {file_name}: {error_msg}")
        
        # Update document status to failed
        if doc_id:
            indexer.update_document_status(doc_id, "failed")
            event_publisher.publish_failed(customer_id, doc_id, sid, file_name, error_msg)
        
        raise

"""Setup Azure AI Search indexes for EWA system."""

import argparse
import os
import sys
from typing import Dict, Any

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def create_ewa_docs_index(client: SearchIndexClient):
    """Create ewa-docs index for report metadata."""
    fields = [
        SimpleField(name="doc_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="customer_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="sid", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="environment", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="report_date", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SimpleField(name="analysis_from", type=SearchFieldDataType.DateTimeOffset, filterable=True),
        SimpleField(name="analysis_to", type=SearchFieldDataType.DateTimeOffset, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="file_name", type=SearchFieldDataType.String),
        SimpleField(name="pages", type=SearchFieldDataType.Int32),
        SimpleField(name="sha256", type=SearchFieldDataType.String),
        SimpleField(name="source_url", type=SearchFieldDataType.String),
        SimpleField(name="processing_status", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="alert_count", type=SearchFieldDataType.Int32),
    ]
    
    index = SearchIndex(name="ewa-docs", fields=fields)
    client.create_or_update_index(index)
    print("Created index: ewa-docs")


def create_ewa_chunks_index(client: SearchIndexClient):
    """Create ewa-chunks index for vector search."""
    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="customer_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="sid", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="environment", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="report_date", type=SearchFieldDataType.DateTimeOffset, filterable=True),
        SearchableField(name="section_path", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_start", type=SearchFieldDataType.Int32),
        SimpleField(name="page_end", type=SearchFieldDataType.Int32),
        SimpleField(name="severity", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="sap_note_ids", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SearchableField(name="content_md", type=SearchFieldDataType.String, retrievable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            retrievable=False,
            stored=False,
            vector_search_dimensions=1536,
            vector_search_profile_name="vector-profile-1"
        ),
        SimpleField(name="parent_chunk_id", type=SearchFieldDataType.String),
        SimpleField(name="header_level", type=SearchFieldDataType.Int32),
    ]
    
    # Vector search configuration
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-1",
                parameters={
                    "m": 4,
                    "efConstruction": 400,
                    "efSearch": 500,
                    "metric": "cosine"
                }
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile-1",
                algorithm_configuration_name="hnsw-1"
            )
        ]
    )
    
    # Semantic search configuration
    semantic_config = SemanticConfiguration(
        name="ewa-semantic",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="section_path"),
            content_fields=[SemanticField(field_name="content_md")],
            keywords_fields=[
                SemanticField(field_name="sid"),
                SemanticField(field_name="category"),
                SemanticField(field_name="severity")
            ]
        )
    )
    
    semantic_search = SemanticSearch(configurations=[semantic_config])
    
    index = SearchIndex(
        name="ewa-chunks",
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search
    )
    client.create_or_update_index(index)
    print("Created index: ewa-chunks")


def create_ewa_alerts_index(client: SearchIndexClient):
    """Create ewa-alerts index for alert storage."""
    fields = [
        SimpleField(name="alert_id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="customer_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="doc_id", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="sid", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="environment", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="report_date", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="severity", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="category", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="section_path", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page_start", type=SearchFieldDataType.Int32),
        SimpleField(name="page_end", type=SearchFieldDataType.Int32),
        SimpleField(name="page_range", type=SearchFieldDataType.String),
        SimpleField(name="evidence_chunk_ids", type=SearchFieldDataType.Collection(SearchFieldDataType.String)),
        SimpleField(name="sap_note_ids", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SimpleField(name="tags", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
        SearchableField(name="description", type=SearchFieldDataType.String),
        SearchableField(name="recommendation", type=SearchFieldDataType.String),
    ]
    
    # Semantic search configuration
    semantic_config = SemanticConfiguration(
        name="ewa-semantic",
        prioritized_fields=SemanticPrioritizedFields(
            title_field=SemanticField(field_name="title"),
            content_fields=[SemanticField(field_name="title")],
            keywords_fields=[
                SemanticField(field_name="sid"),
                SemanticField(field_name="category"),
                SemanticField(field_name="severity")
            ]
        )
    )
    
    semantic_search = SemanticSearch(configurations=[semantic_config])
    
    index = SearchIndex(
        name="ewa-alerts",
        fields=fields,
        semantic_search=semantic_search
    )
    client.create_or_update_index(index)
    print("Created index: ewa-alerts")


def main():
    parser = argparse.ArgumentParser(description="Setup Azure AI Search indexes for EWA")
    parser.add_argument("--endpoint", required=True, help="Azure AI Search endpoint")
    parser.add_argument("--api-key", required=True, help="Azure AI Search admin API key")
    parser.add_argument("--delete-existing", action="store_true", help="Delete existing indexes before creating")
    
    args = parser.parse_args()
    
    # Create client
    credential = AzureKeyCredential(args.api_key)
    client = SearchIndexClient(endpoint=args.endpoint, credential=credential)
    
    # Delete existing if requested
    if args.delete_existing:
        for index_name in ["ewa-docs", "ewa-chunks", "ewa-alerts"]:
            try:
                client.delete_index(index_name)
                print(f"Deleted existing index: {index_name}")
            except Exception as e:
                print(f"Index {index_name} does not exist or could not be deleted: {e}")
    
    # Create indexes
    create_ewa_docs_index(client)
    create_ewa_chunks_index(client)
    create_ewa_alerts_index(client)
    
    print("\nAll indexes created successfully!")
    print(f"Endpoint: {args.endpoint}")
    print("Indexes: ewa-docs, ewa-chunks, ewa-alerts")


if __name__ == "__main__":
    main()

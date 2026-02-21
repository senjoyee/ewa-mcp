"""ask_ewa_scoped tool - RAG query across EWA reports for a customer."""

import json
import os
from typing import TYPE_CHECKING, List, Optional
from mcp.types import Tool
import openai

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="ask_ewa_scoped",
        description=(
            "Answer a free-text question by searching across all EWA reports for a customer. "
            "Uses hybrid (keyword + vector) search to retrieve the most relevant chunks and "
            "returns them together with citations so the caller can formulate an answer."
        ),
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "query"],
            "properties": {
                "customer_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Customer tenant ID"
                },
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Natural language question or search query"
                },
                "sid": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optionally restrict search to a specific SAP System ID"
                },
                "doc_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optionally restrict search to a specific report"
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 12,
                    "description": "Number of relevant chunks to return"
                }
            }
        }
    )


def _get_embedding_client() -> openai.OpenAI:
    """Build an OpenAI client pointing at Azure AI Foundry for embeddings."""
    endpoint = os.environ["AZURE_AI_FOUNDRY_ENDPOINT"].rstrip("/") + "/"
    api_key = os.environ["AZURE_AI_FOUNDRY_API_KEY"]
    return openai.OpenAI(api_key=api_key, base_url=endpoint)


def _embed_query(query: str) -> List[float]:
    """Generate an embedding vector for the search query."""
    client = _get_embedding_client()
    deployment = os.environ.get("AZURE_AI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
    response = client.embeddings.create(
        model=deployment,
        input=[query[:8000]],
        dimensions=1536,
    )
    return response.data[0].embedding


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute ask_ewa_scoped tool."""
    customer_id = arguments["customer_id"]
    query = arguments["query"]
    sid = arguments.get("sid")
    doc_id = arguments.get("doc_id")
    top_k = arguments.get("top_k", 12)

    # Build optional extra filters
    filters = {}
    if sid:
        filters["sid"] = sid
    if doc_id:
        filters["doc_id"] = doc_id

    # Generate query embedding
    try:
        vector = _embed_query(query)
    except Exception as e:
        # Fall back to keyword-only search if embedding fails
        vector = None

    # Search
    if vector is not None:
        chunks = await search_client.hybrid_search(
            customer_id=customer_id,
            query=query,
            vector=vector,
            filters=filters if filters else None,
            top_k=top_k,
        )
    else:
        # Keyword fallback
        chunks = await search_client.get_chunks(
            customer_id=customer_id,
            doc_id=doc_id,
            top_n=top_k,
        )

    result = {
        "query": query,
        "customer_id": customer_id,
        "chunks_found": len(chunks),
        "results": [],
    }

    for chunk in chunks:
        item = {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "sid": chunk.sid,
            "section_path": chunk.section_path,
            "page_range": f"{chunk.page_start}-{chunk.page_end}",
            "content": chunk.content_md,
            "score": getattr(chunk, "score", None),
            "reranker_score": getattr(chunk, "reranker_score", None),
            "citation": {
                "doc_id": chunk.doc_id,
                "section_path": chunk.section_path,
                "page_range": f"{chunk.page_start}-{chunk.page_end}",
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_id": chunk.chunk_id,
                "quote": chunk.content_md[:200] if chunk.content_md else "",
            },
        }
        result["results"].append(item)

    return json.dumps(result, indent=2)

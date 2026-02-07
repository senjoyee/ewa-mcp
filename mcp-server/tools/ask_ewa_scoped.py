"""ask_ewa_scoped tool - RAG query with vector search."""

import json
import os
from typing import TYPE_CHECKING
from mcp.types import Tool
import openai

if TYPE_CHECKING:
    from mcp_server.search.client import SearchClient


def get_tool_definition() -> Tool:
    """Get tool definition."""
    return Tool(
        name="ask_ewa_scoped",
        description="Ask a question about EWA reports using AI-powered search",
        inputSchema={
            "type": "object",
            "additionalProperties": False,
            "required": ["customer_id", "question"],
            "properties": {
                "customer_id": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Customer tenant ID"
                },
                "question": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Question to ask about the EWA reports"
                },
                "filters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "sid": {"type": "string", "description": "Filter by SAP System ID"},
                        "doc_id": {"type": "string", "description": "Filter by specific report"},
                        "date_from": {"type": "string", "format": "date", "description": "From date (YYYY-MM-DD)"},
                        "date_to": {"type": "string", "format": "date", "description": "To date (YYYY-MM-DD)"},
                        "severity": {
                            "type": "string",
                            "enum": ["very_high", "high", "medium", "low", "info", "unknown"]
                        },
                        "category": {
                            "type": "string",
                            "enum": ["security", "performance", "stability", "configuration", "lifecycle", "data_volume", "database", "bw", "other", "unknown"]
                        },
                        "section_contains": {"type": "string", "description": "Section path contains this text"}
                    }
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 12,
                    "description": "Number of chunks to retrieve"
                },
                "answer_style": {
                    "type": "string",
                    "enum": ["concise", "detailed"],
                    "default": "concise",
                    "description": "Answer style"
                }
            }
        }
    )


def _get_embedding(text: str) -> list:
    """Generate embedding for query text."""
    client = openai.AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version="2023-05-15"
    )
    
    response = client.embeddings.create(
        model=os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
        input=text[:8000]
    )
    
    return response.data[0].embedding


async def execute(search_client: "SearchClient", arguments: dict) -> str:
    """Execute ask_ewa_scoped tool."""
    customer_id = arguments["customer_id"]
    question = arguments["question"]
    filters = arguments.get("filters", {})
    top_k = arguments.get("top_k", 12)
    answer_style = arguments.get("answer_style", "concise")
    
    # Generate embedding for the question
    query_vector = _get_embedding(question)
    
    # Perform hybrid search
    chunks = await search_client.hybrid_search(
        customer_id=customer_id,
        query=question,
        vector=query_vector,
        filters=filters if filters else None,
        top_k=top_k
    )
    
    if not chunks:
        return json.dumps({
            "answer": "No relevant information found in the EWA reports for your query.",
            "sources": [],
            "citations": []
        }, indent=2)
    
    # Build context from chunks
    context_parts = []
    for i, chunk in enumerate(chunks[:5]):  # Top 5 chunks for context
        context_parts.append(f"[Source {i+1}] {chunk.section_path} (Page {chunk.page_start}-{chunk.page_end}):\n{chunk.content_md[:800]}")
    
    context = "\n\n".join(context_parts)
    
    # Build citations
    citations = []
    for chunk in chunks[:5]:
        citations.append({
            "doc_id": chunk.doc_id,
            "section_path": chunk.section_path,
            "page_range": f"{chunk.page_start}-{chunk.page_end}",
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "chunk_id": chunk.chunk_id,
            "quote": chunk.content_md[:300] if chunk.content_md else ""
        })
    
    # Generate answer using GPT
    answer = _generate_answer(question, context, answer_style)
    
    # Build source summary
    sources = []
    seen_docs = set()
    for chunk in chunks[:5]:
        if chunk.doc_id not in seen_docs:
            sources.append({
                "doc_id": chunk.doc_id,
                "sid": chunk.sid,
                "sections": [chunk.section_path]
            })
            seen_docs.add(chunk.doc_id)
    
    result = {
        "question": question,
        "answer": answer,
        "sources": sources,
        "chunks_retrieved": len(chunks),
        "citations": citations
    }
    
    return json.dumps(result, indent=2)


def _generate_answer(question: str, context: str, style: str) -> str:
    """Generate answer from context using GPT."""
    client = openai.AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version="2024-12-01-preview"
    )
    
    if style == "concise":
        system_prompt = "You are a technical consultant answering questions about SAP EarlyWatch Alert reports. Answer concisely based only on the provided context. If the answer is not in the context, say so."
    else:
        system_prompt = "You are a technical consultant answering questions about SAP EarlyWatch Alert reports. Provide a detailed answer based on the provided context. Include specific findings and recommendations from the reports."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context from EWA reports:\n\n{context}\n\nQuestion: {question}\n\nAnswer:"}
    ]
    
    response = client.chat.completions.create(
        model=os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o"),
        messages=messages,
        max_tokens=800 if style == "concise" else 1500,
        temperature=0.3
    )
    
    return response.choices[0].message.content

# SAP EarlyWatch Alert MCP + Azure AI Search System

A containerized system that ingests SAP EWA PDFs, extracts alerts using GPT-5.2 Vision, chunks content via markdown headers, vectorizes with Azure OpenAI, stores in Azure AI Search (multi-tenant shared indexes), and exposes an MCP server over Streamable HTTP for Copilot/Claude Desktop integration.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Multi-tenancy | Shared indexes with `customer_id` field | Easier index management, requires filter in all queries |
| Alert extraction | GPT-5.2 Vision on pages 1-4 as images | EWA priority tables are visually structured, vision models parse them accurately |
| Chunking | Markdown header-based (h1, h2, h3) | Preserves EWA's hierarchical section structure |
| Embedding | text-embedding-3-small (1536d) | Cost-effective, sufficient quality for technical docs |
| MCP transport | Streamable HTTP | Modern replacement for SSE, better connection handling |
| Deployment | Azure Container Apps | Good for persistent HTTP connections, easy scaling |
| Auth | API Key in Authorization header | Simple, stateless, suitable for internal tools |
| Processing status | Event Grid events | Real-time status tracking, decoupled architecture |

## System Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   EWA PDF       │────▶│  Azure Blob      │────▶│  Azure Function │
│   Upload        │     │  Storage         │     │  (Blob Trigger) │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                         │
                              ┌──────────────────────────┼──────────┐
                              │                          │          │
                              ▼                          ▼          ▼
                    ┌─────────────────┐        ┌──────────────┐  ┌──────────┐
                    │  Event Grid     │        │  GPT-5.2      │  │ pypdf/   │
                    │  (status events) │        │  Vision      │  │ pymupdf4llm│
                    └─────────────────┘        │  (alerts)    │  │ (full text)│
                                               └──────┬───────┘  └────┬─────┘
                                                      │               │
                                                      ▼               ▼
                                               ┌─────────────────────────┐
                                               │  Markdown + Alert JSON  │
                                               └───────────┬─────────────┘
                                                           │
                           ┌─────────────────────────────────┼─────────────────────┐
                           │                                 │                     │
                           ▼                                 ▼                     ▼
                   ┌───────────────┐               ┌─────────────────┐    ┌──────────────────┐
                   │  Markdown     │               │  Azure OpenAI   │    │  Alert metadata  │
                   │  Header-based │──────────────▶│  Embedding      │    │  (ewa-alerts)    │
                   │  Chunking     │               │  (text-3-small) │    │  index           │
                   └───────────────┘               └────────┬────────┘    └──────────────────┘
                                                            │
                                                            ▼
                                                   ┌──────────────────┐
                                                   │  ewa-chunks      │
                                                   │  index (vectors) │
                                                   └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              MCP Server (ACA)                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
│  │list_reports │  │get_alert_   │  │ask_ewa_     │  │  Streamable HTTP    ││
│  │             │  │overview     │  │scoped       │  │  (MCP 2024-11-05)   ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │  Copilot / Claude     │
                          │  Desktop              │
                          └───────────────────────┘
```

## Component Breakdown

### 1. Document Processing Pipeline (`/processor/`)

**Architecture:** Azure Function (Python, Flex Consumption) triggered by Blob Storage

| File | Purpose |
|------|---------|
| `function_app.py` | Main entry point, blob trigger handler |
| `extractors/pdf_extractor.py` | pypdf/pymupdf4llm integration for full-text markdown |
| `extractors/alert_extractor.py` | GPT-4o Vision client for pages 1-4 image extraction |
| `chunkers/markdown_chunker.py` | Header-based chunking (h1, h2, h3 boundaries) |
| `embedders/openai_embedder.py` | Azure OpenAI text-embedding-3-small client |
| `indexers/search_indexer.py` | Azure AI Search document uploader |
| `eventgrid/publisher.py` | Event Grid event publishing for status updates |
| `models/schemas.py` | Pydantic models for alerts, chunks, events |

**Processing Flow:**
1. Blob trigger fires on PDF upload to `ewa-uploads/{customer_id}/{filename}`
2. Emit `EwaProcessingStarted` event to Event Grid
3. Extract pages 1-4 as images → GPT-4o Vision → structured alert JSON
4. Extract full PDF text → markdown via pymupdf4llm
5. Chunk markdown by headers (preserve section_path)
6. Embed chunks via Azure OpenAI
7. Upload to 3 indexes: `ewa-docs`, `ewa-chunks`, `ewa-alerts`
8. Emit `EwaProcessingCompleted` or `EwaProcessingFailed` event

**Event Schema:**
```json
{
  "eventType": "EwaProcessingStarted|EwaProcessingCompleted|EwaProcessingFailed",
  "subject": "/ewa/{customer_id}/{doc_id}",
  "data": {
    "customer_id": "string",
    "doc_id": "string", 
    "sid": "string",
    "filename": "string",
    "stage": "extracting|chunking|embedding|indexing",
    "error": "string (on failure)"
  }
}
```

### 2. MCP Server (`/mcp-server/`)

**Architecture:** FastAPI with MCP Streamable HTTP transport, deployed to Azure Container Apps

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, MCP server initialization |
| `transports/streamable_http.py` | MCP Streamable HTTP transport implementation |
| `tools/list_reports.py` | Query `ewa-docs` index with customer filter |
| `tools/get_alert_overview.py` | Query `ewa-alerts` by doc_id |
| `tools/get_alert_detail.py` | Fetch alert + linked chunks from `ewa-chunks` |
| `tools/get_section.py` | Retrieve specific section_path from `ewa-chunks` |
| `tools/ask_ewa_scoped.py` | Vector search + hybrid search on `ewa-chunks` |
| `tools/compare_reports.py` | Diff alerts between two reports |
| `tools/generate_action_pack.py` | Aggregate alerts into deliverable package |
| `auth/api_key.py` | API Key validation middleware |
| `search/client.py` | Azure AI Search async client wrapper |
| `models/responses.py` | Response models with Citation schema |

**Tool-to-Index Mapping:**
| Tool | Primary Index | Key Query |
|------|--------------|-----------|
| `list_reports` | `ewa-docs` | `$filter=customer_id eq '{customer_id}'` |
| `get_alert_overview` | `ewa-alerts` | `$filter=customer_id eq '{customer_id}' and doc_id eq '{doc_id}'` |
| `get_alert_detail` | `ewa-alerts` + `ewa-chunks` | Lookup alert, then fetch chunks by `evidence_chunk_ids` |
| `get_section` | `ewa-chunks` | `$filter=customer_id eq '{customer_id}' and doc_id eq '{doc_id}' and section_path eq '{path}'` |
| `ask_ewa_scoped` | `ewa-chunks` | Vector search with `customer_id` filter + optional semantic reranking |

### 3. Azure AI Search Index Schemas

All indexes are **shared multi-tenant** with `customer_id` as a required filter field.

**Index: `ewa-docs`** (report inventory)
```json
{
  "fields": [
    { "name": "doc_id", "type": "Edm.String", "key": true },
    { "name": "customer_id", "type": "Edm.String", "filterable": true },
    { "name": "sid", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "environment", "type": "Edm.String", "filterable": true },
    { "name": "report_date", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true },
    { "name": "analysis_from", "type": "Edm.DateTimeOffset" },
    { "name": "analysis_to", "type": "Edm.DateTimeOffset" },
    { "name": "title", "type": "Edm.String", "searchable": true },
    { "name": "file_name", "type": "Edm.String" },
    { "name": "pages", "type": "Edm.Int32" },
    { "name": "sha256", "type": "Edm.String" },
    { "name": "processing_status", "type": "Edm.String", "filterable": true }
  ]
}
```

**Index: `ewa-chunks`** (vector search)
```json
{
  "fields": [
    { "name": "chunk_id", "type": "Edm.String", "key": true },
    { "name": "doc_id", "type": "Edm.String", "filterable": true },
    { "name": "customer_id", "type": "Edm.String", "filterable": true },
    { "name": "sid", "type": "Edm.String", "filterable": true },
    { "name": "environment", "type": "Edm.String", "filterable": true },
    { "name": "report_date", "type": "Edm.DateTimeOffset", "filterable": true },
    { "name": "section_path", "type": "Edm.String", "filterable": true, "searchable": true },
    { "name": "page_start", "type": "Edm.Int32" },
    { "name": "page_end", "type": "Edm.Int32" },
    { "name": "severity", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "category", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "sap_note_ids", "type": "Collection(Edm.String)", "filterable": true },
    { "name": "content_md", "type": "Edm.String", "searchable": true, "retrievable": true },
    { "name": "content_vector", "type": "Collection(Edm.Single)", "dimensions": 1536, "vectorSearchProfile": "vector-profile-1", "stored": false }
  ],
  "vectorSearch": {
    "algorithms": [{ "name": "hnsw-1", "kind": "hnsw", "hnswParameters": { "m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine" } }],
    "profiles": [{ "name": "vector-profile-1", "algorithm": "hnsw-1" }]
  },
  "semantic": {
    "configurations": [{
      "name": "ewa-semantic",
      "prioritizedFields": {
        "titleField": { "fieldName": "section_path" },
        "prioritizedContentFields": [{ "fieldName": "content_md" }],
        "prioritizedKeywordsFields": [{ "fieldName": "sid" }, { "fieldName": "category" }, { "fieldName": "severity" }]
      }
    }]
  }
}
```

**Index: `ewa-alerts`**
```json
{
  "fields": [
    { "name": "alert_id", "type": "Edm.String", "key": true },
    { "name": "customer_id", "type": "Edm.String", "filterable": true },
    { "name": "doc_id", "type": "Edm.String", "filterable": true },
    { "name": "sid", "type": "Edm.String", "filterable": true },
    { "name": "environment", "type": "Edm.String", "filterable": true },
    { "name": "report_date", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true },
    { "name": "title", "type": "Edm.String", "searchable": true },
    { "name": "severity", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "category", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "section_path", "type": "Edm.String", "filterable": true },
    { "name": "page_start", "type": "Edm.Int32" },
    { "name": "page_end", "type": "Edm.Int32" },
    { "name": "page_range", "type": "Edm.String" },
    { "name": "evidence_chunk_ids", "type": "Collection(Edm.String)" },
    { "name": "sap_note_ids", "type": "Collection(Edm.String)" },
    { "name": "tags", "type": "Collection(Edm.String)", "filterable": true }
  ]
}
```

## Directory Structure

```
/ewa-mcp-system
├── /processor                    # Azure Function (Python)
│   ├── function_app.py
│   ├── host.json
│   ├── local.settings.json
│   ├── requirements.txt
│   ├── /extractors
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py      # pymupdf4llm
│   │   └── alert_extractor.py    # GPT-4o Vision
│   ├── /chunkers
│   │   ├── __init__.py
│   │   └── markdown_chunker.py   # Header-based chunking
│   ├── /embedders
│   │   ├── __init__.py
│   │   └── openai_embedder.py
│   ├── /indexers
│   │   ├── __init__.py
│   │   └── search_indexer.py
│   ├── /eventgrid
│   │   ├── __init__.py
│   │   └── publisher.py
│   └── /models
│       ├── __init__.py
│       └── schemas.py
│
├── /mcp-server                   # FastAPI + MCP (Azure Container Apps)
│   ├── Dockerfile
│   ├── main.py
│   ├── requirements.txt
│   ├── /transports
│   │   ├── __init__.py
│   │   └── streamable_http.py    # MCP HTTP streaming
│   ├── /tools
│   │   ├── __init__.py
│   │   ├── list_reports.py
│   │   ├── get_alert_overview.py
│   │   ├── get_alert_detail.py
│   │   ├── get_section.py
│   │   ├── ask_ewa_scoped.py
│   │   ├── compare_reports.py
│   │   └── generate_action_pack.py
│   ├── /auth
│   │   ├── __init__.py
│   │   └── api_key.py
│   ├── /search
│   │   ├── __init__.py
│   │   └── client.py
│   └── /models
│       ├── __init__.py
│       └── responses.py
│
├── /infrastructure               # Terraform / Bicep
│   ├── /bicep
│   │   ├── main.bicep
│   │   ├── search.bicep
│   │   ├── function.bicep
│   │   ├── containerapp.bicep
│   │   └── eventgrid.bicep
│   └── /scripts
│       ├── deploy.sh
│       └── setup-indexes.py
│
├── /shared                       # Shared models/contracts
│   └── /models
│       ├── alert.py
│       ├── chunk.py
│       └── citation.py
│
├── /tests
│   ├── /processor
│   ├── /mcp-server
│   └── /integration
│
├── .env.example
├── .gitignore
└── README.md
```

## Configuration Schema

**`/processor/local.settings.json`:**
```json
{
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "BLOB_CONNECTION_STRING": "@Microsoft.KeyVault(...)",
    "BLOB_CONTAINER_NAME": "ewa-uploads",
    "AZURE_OPENAI_ENDPOINT": "https://{resource}.openai.azure.com/",
    "AZURE_OPENAI_API_KEY": "@Microsoft.KeyVault(...)",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
    "AZURE_OPENAI_VISION_DEPLOYMENT": "gpt-5.2",
    "AZURE_SEARCH_ENDPOINT": "https://{resource}.search.windows.net",
    "AZURE_SEARCH_API_KEY": "@Microsoft.KeyVault(...)",
    "EVENTGRID_ENDPOINT": "https://{topic}.westus2-1.eventgrid.azure.net/api/events",
    "EVENTGRID_KEY": "@Microsoft.KeyVault(...)"
  }
}
```

**`/mcp-server/.env`:**
```env
# Server
PORT=8000
API_KEY_HEADER=Authorization
API_KEY_VALUE=Bearer sk-ewa-...

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://{resource}.search.windows.net
AZURE_SEARCH_API_KEY=...
INDEX_DOCS=ewa-docs
INDEX_CHUNKS=ewa-chunks
INDEX_ALERTS=ewa-alerts

# Azure OpenAI (for ask_ewa_scoped generation)
AZURE_OPENAI_ENDPOINT=https://{resource}.openai.azure.com/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5.2
```

## Critical Implementation Details

### Alert Extraction (GPT-5.2 Vision)

Pages 1-4 of EWA contain priority tables. Extract as images → GPT-5.2 with structured output:

```python
alert_extraction_prompt = """
Extract all alerts from this SAP EarlyWatch Alert priority table.
For each alert, return:
- title: alert name/description
- severity: one of [very_high, high, medium, low, info]
- category: one of [security, performance, stability, configuration, lifecycle, data_volume, database, bw, other]
- sap_note_ids: list of SAP note numbers mentioned (if any)
- page_range: page number where this alert appears

Output as JSON array.
"""
```

### Markdown Header-Based Chunking

```python
def chunk_by_headers(markdown: str, doc_id: str) -> List[Chunk]:
    """Split markdown by headers (h1, h2, h3) preserving hierarchy."""
    # Use regex to split on headers while capturing header level
    # Track section_path like "1. System Overview/1.1 Hardware"
    # Each chunk gets: chunk_id, section_path, content_md, page_start, page_end
    # Link chunks to alerts via evidence_chunk_ids (same section_path/page_range)
```

### Multi-tenant Query Pattern

Every query to Azure AI Search MUST include customer_id filter:

```python
# Pattern for ALL tools
filter_clause = f"customer_id eq '{customer_id}'"
if sid:
    filter_clause += f" and sid eq '{sid}'"
if doc_id:
    filter_clause += f" and doc_id eq '{doc_id}'"

# Vector search with filter
vector_query = VectorizableTextQuery(
    text=question,
    k_nearest_neighbors=top_k,
    fields="content_vector",
    filter=filter_clause  # Critical: always filter by customer_id
)
```

### Citation Contract

Every tool response includes citations array:

```python
class Citation(BaseModel):
    doc_id: str
    section_path: str
    page_range: str
    page_start: int
    page_end: int
    chunk_id: Optional[str]
    source_url: Optional[str]
    quote: Optional[str]  # Snippet of evidence
```

## Deployment Steps

1. **Infrastructure (Bicep):**
   - Deploy Azure AI Search (S1 or higher for semantic ranking)
   - Deploy Azure OpenAI (text-embedding-3-small + gpt-4o deployments)
   - Deploy Storage Account with blob container `ewa-uploads`
   - Deploy Event Grid topic `ewa-processing-events`
   - Deploy Container Apps Environment for MCP server

2. **Search Indexes:**
   ```bash
   python infrastructure/scripts/setup-indexes.py \
     --endpoint $AZURE_SEARCH_ENDPOINT \
     --api-key $AZURE_SEARCH_API_KEY
   ```

3. **Processor (Azure Function):**
   ```bash
   cd processor
   func azure functionapp publish $FUNCTION_APP_NAME
   ```

4. **MCP Server (Container Apps):**
   ```bash
   cd mcp-server
   az acr build --registry $ACR_NAME --image ewa-mcp:latest .
   az containerapp update --name ewa-mcp --resource-group $RG --image $ACR_NAME.azurecr.io/ewa-mcp:latest
   ```

5. **Client Configuration:**
   - Claude Desktop: Add to `claude_desktop_config.json`
   - Copilot: Register as custom MCP endpoint

## Testing Checklist

- [ ] Upload PDF to blob storage → verify Event Grid events fire
- [ ] Verify alerts extracted from pages 1-4 with correct severity/category
- [ ] Verify chunks created with proper section_path hierarchy
- [ ] Verify all chunks have embeddings (1536 dimensions)
- [ ] Query `list_reports` → only returns reports for specified customer_id
- [ ] Query `ask_ewa_scoped` → vector search returns relevant chunks with citations
- [ ] Query `get_alert_detail` → returns alert + linked evidence chunks
- [ ] Verify cross-customer isolation (customer A cannot see customer B data)
- [ ] Verify API Key rejection on invalid key

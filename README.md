# SAP EarlyWatch Alert MCP System

A containerized system that ingests SAP EWA PDFs, extracts alerts using GPT-5.2 Vision, chunks content via markdown headers, vectorizes with Azure OpenAI, stores in Azure AI Search (multi-tenant shared indexes), and exposes an MCP server over Streamable HTTP for Copilot/Claude Desktop integration.

## Architecture

```
EWA PDF Upload → Blob Storage → Azure Function → GPT-5.2 Vision (alerts) + pymupdf4llm (text)
                                          ↓
                        Markdown Header Chunking → OpenAI Embedding → Azure AI Search
                                          ↓
                                MCP Server (ACA) ← Event Grid (status events)
                                          ↓
                                Copilot / Claude Desktop
```

## Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Document Processor | Azure Function (Python) | PDF extraction, alert extraction, chunking, embedding |
| MCP Server | FastAPI + MCP SDK | Streamable HTTP MCP endpoint |
| Vector Store | Azure AI Search | Document, chunk, and alert storage |
| Embeddings | Azure OpenAI text-embedding-3-small | 1536-dimension vectors |
| Alert Extraction | Azure OpenAI GPT-5.2 Vision | Pages 1-4 image analysis |
| Events | Azure Event Grid | Processing status tracking |

## Quick Start

### 1. Deploy Infrastructure

```bash
cd infrastructure/bicep
az deployment group create \
  --resource-group ewa-mcp-rg \
  --template-file main.bicep \
  --parameters environment=prod \
  --parameters personResponsible="Your Name"  # Required tag
```

### 2. Setup Search Indexes

```bash
python infrastructure/scripts/setup-indexes.py \
  --endpoint $AZURE_SEARCH_ENDPOINT \
  --api-key $AZURE_SEARCH_API_KEY
```

### 3. Deploy Document Processor

```bash
cd processor
func azure functionapp publish ewa-processor-prod
```

### 4. Deploy MCP Server

```bash
cd mcp-server
az acr build --registry ewaacr --image ewa-mcp:latest .
az containerapp update --name ewa-mcp --image ewaacr.azurecr.io/ewa-mcp:latest
```

### 5. Configure MCP Client

Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "ewa": {
      "url": "https://ewa-mcp.your-region.azurecontainerapps.io/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key"
      }
    }
  }
}
```

### Using Existing OpenAI Deployment

If you already have an OpenAI deployment with `gpt-5.2` and `text-embedding-3-small`, you can skip creating a new one:

**Option 1: With deploy.py script**
```bash
python deploy.py \
  --subscription <id> \
  --resource-group ewa-mcp-rg \
  --person-responsible "Your Name" \
  --use-existing-openai \
  --openai-endpoint "https://your-openai.openai.azure.com/" \
  --openai-key "your-api-key"
```

**Option 2: Manual Bicep deployment**
```bash
az deployment group create \
  --resource-group ewa-mcp-rg \
  --template-file infrastructure/bicep/main.bicep \
  --parameters environment=prod \
  --parameters personResponsible="Your Name" \
  --parameters deployOpenAI=false \
  --parameters existingOpenAIEndpoint="https://your-openai.openai.azure.com/" \
  --parameters existingOpenAIKey="your-api-key"
```

This will use your existing deployment for both GPT-5.2 Vision alert extraction and text-embedding-3-small vectorization.

## MCP Tools

| Tool | Description |
|------|-------------|
| `list_reports` | List available EWA reports for a customer |
| `get_alert_overview` | Get all alerts from a report |
| `get_alert_detail` | Get detailed alert with evidence chunks |
| `get_section` | Retrieve specific document section |
| `ask_ewa_scoped` | RAG query across reports |
| `compare_reports` | Compare alerts between two reports |
| `generate_action_pack` | Generate deliverable action package |

## Directory Structure

```
/ewa-mcp
├── /processor              # Azure Function for PDF processing
│   ├── extractors/         # PDF extraction, GPT-5.2 Vision
│   ├── chunkers/           # Markdown chunking
│   ├── embedders/          # OpenAI embeddings
│   ├── indexers/           # Azure AI Search indexing
│   └── eventgrid/          # Event Grid publisher
├── /mcp-server             # FastAPI MCP server
│   ├── tools/              # MCP tool implementations
│   ├── search/             # Search client wrapper
│   └── auth/               # API key middleware
├── /infrastructure         # Bicep templates
│   ├── bicep/              # ARM/Bicep templates
│   └── scripts/            # Setup scripts
├── /shared                 # Shared Pydantic models
│   └── models/             # Alert, Chunk, Document, Citation
└── /tests                  # Test suites
```

## Configuration

### Processor (Azure Function)

```json
{
  "AZURE_OPENAI_ENDPOINT": "https://...openai.azure.com/",
  "AZURE_OPENAI_API_KEY": "...",
  "AZURE_OPENAI_VISION_DEPLOYMENT": "gpt-5.2",
  "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": "text-embedding-3-small",
  "AZURE_SEARCH_ENDPOINT": "https://...search.windows.net",
  "AZURE_SEARCH_API_KEY": "...",
  "EVENTGRID_ENDPOINT": "https://...eventgrid.azure.net",
  "EVENTGRID_KEY": "..."
}
```

### MCP Server

```env
AZURE_SEARCH_ENDPOINT=https://...search.windows.net
AZURE_SEARCH_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://...openai.azure.com/
AZURE_OPENAI_API_KEY=...
API_KEY=your-secure-api-key
PORT=8000
```

## Multi-Tenancy

All indexes are shared multi-tenant with `customer_id` as a required filter field. Every query MUST include customer_id filtering for data isolation.

## Processing Flow

1. Upload PDF to `ewa-uploads/{customer_id}/{filename}`
2. Blob trigger fires Azure Function
3. Emit `EwaProcessingStarted` event
4. Extract pages 1-4 as images → GPT-5.2 Vision → structured alerts
5. Extract full PDF text → markdown via pymupdf4llm
6. Chunk markdown by headers (preserve section_path)
7. Generate embeddings (1536d)
8. Upload to 3 indexes: `ewa-docs`, `ewa-chunks`, `ewa-alerts`
9. Emit `EwaProcessingCompleted` event

## License

MIT

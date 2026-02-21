# EWA MCP Deployment Inventory

| Attribute | Value |
|-----------|-------|
| Deployment Date | 2026-02-20 |
| Resource Group | ewa-mcp-rg |
| Location | uksouth (Registry in eastus) |
| Deployed By | joyee.sen@softwareone.com |
| PersonResponsible Tag | joyee.sen@softwareone.com |
| Subscription | 2969c0b7-f92f-49b7-b7e6-d3135583ad6e |

## Azure Resources

| Resource Type | Name | Endpoint/Details |
|--------------|------|------------------|
| Azure AI Search | ewa-search | https://ewa-search.search.windows.net |
| Storage Account | ewastgw2gtkdzdemu7s | Blob: ewa-uploads |
| Event Grid Topic | ewa-events | https://ewa-events.uksouth-1.eventgrid.azure.net/api/events |
| Container App Environment | ewa-env | Managed environment for hosting MCP Server |
| Log Analytics Workspace | ewa-logs | Centralized logging and monitoring |
| Azure Function App | ewa-processor-prod | https://ewa-processor-prod.azurewebsites.net |
| App Service Plan | ewa-processor-prod | Linux Consumption Plan (uksouth) |
| Container Registry | ewaacrmcp | ewaacrmcp.azurecr.io (eastus) |
| Container App | ewa-mcp | https://ewa-mcp.gentlesky-9abfedb4.uksouth.azurecontainerapps.io |

## Azure AI Search Indexes

| Index | Purpose |
|-------|---------|
| ewa-docs | Document metadata (filename, customer_id, upload_date, status) |
| ewa-chunks | Markdown chunks with embeddings (content, section_path, parent_doc_id) |
| ewa-alerts | Extracted alerts (severity, category, evidence refs) |

| Attribute | Value |
|-----------|-------|
| Search SKU | basic |
| Search API Key (Primary) | **\<redacted — store in Azure Key Vault or local.settings.json\>** |
| Search API Key (Secondary) | **\<redacted — store in Azure Key Vault or local.settings.json\>** |

## Storage Account

| Attribute | Value |
|-----------|-------|
| Name | ewastgw2gtkdzdemu7s |
| SKU | Standard_LRS |
| Blob Container | ewa-uploads |
| Connection String | **\<redacted — store in Azure Key Vault or local.settings.json\>** |

## Event Grid

| Attribute | Value |
|-----------|-------|
| Name | ewa-events |
| Endpoint | https://ewa-events.uksouth-1.eventgrid.azure.net/api/events |
| Key 1 | **\<redacted — store in Azure Key Vault or local.settings.json\>** |

## Configuration: Processor (Azure Function)

| Environment Variable | Value | Status |
|---------------------|-------|--------|
| BLOB_CONNECTION_STRING | DefaultEndpointsProtocol=https;AccountName=ewastgw2gtkdzdemu7s... | ✅ Configured |
| BLOB_CONTAINER_NAME | ewa-uploads | ✅ Configured |
| AZURE_AI_FOUNDRY_ENDPOINT | https://<project>.<region>.models.ai.azure.com | ⏳ Pending Customer Input |
| AZURE_AI_FOUNDRY_API_KEY | <foundry-api-key> | ⏳ Pending Customer Input |
| AZURE_AI_EMBEDDING_DEPLOYMENT | text-embedding-3-small | ✅ Configured |
| AZURE_AI_VISION_DEPLOYMENT | Kimi-K2.5 | ✅ Configured |
| AZURE_SEARCH_ENDPOINT | https://ewa-search.search.windows.net | ✅ Configured |
| AZURE_SEARCH_API_KEY | **\<redacted\>** | ✅ Configured |
| EVENTGRID_ENDPOINT | https://ewa-events.uksouth-1.eventgrid.azure.net/api/events | ✅ Configured |
| EVENTGRID_KEY | **\<redacted\>** | ✅ Configured |

## Configuration: MCP Server

| Environment Variable | Value | Status |
|---------------------|-------|--------|
| AZURE_SEARCH_ENDPOINT | https://ewa-search.search.windows.net | ✅ Configured |
| AZURE_SEARCH_API_KEY | **\<redacted\>** | ✅ Configured |
| API_KEY | **\<redacted\>** | ✅ Configured |
| PORT | 8000 | ✅ Configured |

## Claude Desktop Configuration

Add the following to your Claude Desktop config file (`%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "ewa": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/create-server",
        "https://ewa-mcp.gentlesky-9abfedb4.uksouth.azurecontainerapps.io/mcp/sse"
      ],
      "env": {
        "API_KEY": "<your-api-key>"
      }
    }
  }
}
```

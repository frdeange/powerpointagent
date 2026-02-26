# PowerPoint Agent 🎯

A multi-agent AI system that generates professional PowerPoint presentations using Azure AI Foundry V2, FastMCP servers, and M365 Agents SDK.

## Architecture

```
User (Web Chat / Teams)
        │
        ▼
   Bot Service (M365 Agents SDK)
        │  DirectLine / Bot Framework
        ▼
  Orchestrator (agent-framework + Azure AI Foundry V2)
        │
        ├── ContentPlanner Agent  ──► Bing Grounding
        ├── ContentWriter Agent   ──► Bing Grounding
        ├── DesignAgent           ──► PPTX MCP Server
        ├── ImageGenerator Agent  ──► Image MCP Server
        ├── DocumentAnalyzer Agent──► PPTX MCP Server (document upload path)
        └── AssemblyAgent         ──► PPTX MCP Server
                │                          │
                └──────────────────────────┤
                                           ▼
                               Azure Blob Storage
                               (templates, generated, images, uploads)
```

## Services

| Service | Description | Deployment |
|---------|-------------|------------|
| `bot` | M365 Agents SDK — Web Chat + Teams | ACA (external) |
| `orchestrator` | agent-framework V2 orchestration | ACA (internal) |
| `pptx-mcp-server` | PPTX tools via FastMCP | ACA (external) |
| `image-mcp-server` | Image tools via FastMCP | ACA (external) |

## Agents

| Agent | Role | Tools |
|-------|------|-------|
| ContentPlanner | Research + outline generation | Bing Grounding |
| ContentWriter | Slide text + speaker notes | Bing Grounding |
| DesignAgent | Layout + visual selection | PPTX MCP: apply_template, choose_layout |
| ImageGenerator | AI image + stock photo | Image MCP: generate_image, search_stock_image |
| DocumentAnalyzer | Extract design + content from uploaded PPTX | PPTX MCP: analyze_pptx_document |
| AssemblyAgent | Build final PPTX file | PPTX MCP: create_presentation, add_slide, export_presentation |

## Quick Start

### Prerequisites

- Python 3.13+
- Azure subscription with AI Foundry project
- Azure Container Registry
- Azure Container Apps environment
- Azure Blob Storage account

### Local Development

```bash
# Clone the repo
git clone https://github.com/frdeange/powerpointagent.git
cd powerpointagent

# Copy environment variables
cp .env.example .env
# Edit .env with your values

# Install dependencies for a service
cd services/orchestrator
pip install -r requirements.txt

# Run a service locally
python main.py
```

### Deployment

```bash
# Deploy all infrastructure
cd infra
az deployment sub create \
  --location eastus2 \
  --template-file main.bicep \
  --parameters main.bicepparam

# Build and push containers
./scripts/deploy.sh
```

## MCP Tools

### PPTX MCP Server (`/mcp`)

| Tool | Description |
|------|-------------|
| `create_presentation` | Initialize a new PPTX file in blob storage |
| `add_slide` | Add a slide with content and layout |
| `apply_template` | Apply a design template to a presentation |
| `add_image_to_slide` | Insert an image into a slide |
| `export_presentation` | Finalize and generate download URL |
| `list_templates` | List available design templates |
| `analyze_pptx_document` | Extract design + content from uploaded PPTX |

### Image MCP Server (`/mcp`)

| Tool | Description |
|------|-------------|
| `generate_image` | Generate AI image via DALL-E 3 |
| `search_stock_image` | Search Bing Images for stock photos |
| `optimize_image` | Resize/compress image for PPTX |

## Document Upload Feature

Users can upload an existing PPTX file to extract its design and content as a starting point. The `DocumentAnalyzer` agent processes the file and feeds the extracted information into the presentation pipeline.

```
Upload PPTX → DocumentAnalyzer → (design_spec + content_outline) → Pipeline
```

## Environment Variables

See [`.env.example`](.env.example) for all required variables.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific service tests
pytest services/pptx-mcp-server/tests/ -v
pytest services/orchestrator/tests/ -v
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT

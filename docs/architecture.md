# Architecture

## Overview

PowerPoint Agent is a multi-agent AI system that generates professional PowerPoint presentations. It uses Azure AI Foundry V2 agents, FastMCP servers on Azure Container Apps, and M365 Agents SDK for bot channel integration.

## Component Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                     User Interfaces                                 │
│  ┌──────────────────────┐      ┌──────────────────────────────┐    │
│  │   Web Chat UI         │      │   Microsoft Teams             │    │
│  │   (BotFramework       │      │   (Teams channel adapter)     │    │
│  │    WebChat widget)    │      │                              │    │
│  └─────────┬────────────┘      └──────────────┬───────────────┘    │
└────────────┼──────────────────────────────────┼────────────────────┘
             │  HTTP (DirectLine)                │  Bot Framework
             ▼                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│              Bot Service (ACA — external ingress)                   │
│              M365 Agents SDK (aiohttp)                              │
│              Port: 3978   /api/messages                            │
└─────────────────────────────┬──────────────────────────────────────┘
                              │  HTTP (internal ACA)
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│           Orchestrator (ACA — internal only)                        │
│           FastAPI + agent-framework V2                             │
│           Port: 8080   /generate  /jobs/{id}  /upload              │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Azure AI Foundry V2 Agents                       │  │
│  │                                                              │  │
│  │  ContentPlanner ──► Bing Grounding                          │  │
│  │  ContentWriter  ──► Bing Grounding                          │  │
│  │  DesignAgent    ──► PPTX MCP Server                        │  │
│  │  ImageGenerator ──► Image MCP Server                       │  │
│  │  DocumentAnalyzer──► PPTX MCP Server (upload path)        │  │
│  │  AssemblyAgent  ──► PPTX MCP Server                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────┬──────────────────────────────────────┘
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐   ┌───────────────────────────────┐
│  PPTX MCP Server         │   │  Image MCP Server             │
│  (ACA — external)        │   │  (ACA — external)             │
│  FastMCP 3.x             │   │  FastMCP 3.x                  │
│  Port: 8000   /mcp       │   │  Port: 8001   /mcp            │
│                          │   │                               │
│  7 Tools:                │   │  3 Tools:                     │
│  • create_presentation   │   │  • generate_image (DALL-E 3)  │
│  • add_slide             │   │  • search_stock_image         │
│  • apply_template        │   │  • optimize_image             │
│  • add_image_to_slide    │   │                               │
│  • export_presentation   │   └───────────────────────────────┘
│  • list_templates        │
│  • analyze_pptx_document │
└──────────────┬───────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────┐
│                   Azure Blob Storage                         │
│  • templates   (design template PPTX files)                  │
│  • generated   (in-progress and final PPTX files)            │
│  • images      (generated/optimized images)                  │
│  • uploads     (user-uploaded PPTX files)                    │
└─────────────────────────────────────────────────────────────┘
```

## Agent Pipeline

### Standard Flow (no document upload)

```
1. ContentPlanner  → Research + create slide outline (Bing Grounding)
2. ContentWriter   → Refine and enrich slide content (Bing Grounding)
3. DesignAgent     → Select template + apply design (PPTX MCP)
4. ImageGenerator  → Generate/find images (Image MCP) [concurrent eligible]
5. AssemblyAgent   → Build final PPTX (PPTX MCP)
```

### Document Upload Flow

```
0. DocumentAnalyzer → Extract design + content from uploaded PPTX
                                ↓
1. ContentPlanner  → Expand/improve extracted outline
2. ContentWriter   → Enrich content
3. DesignAgent     → Apply/preserve design from original
4. ImageGenerator  → Source new images
5. AssemblyAgent   → Assemble final PPTX
```

## MCP Server Design

Both MCP servers use **FastMCP 3.x** with `stateless_http=True`:

```python
mcp = FastMCP("name", stateless_http=True)
mcp.run(transport="http", host="0.0.0.0", port=8000)
# MCP endpoint: /mcp
```

**Important**: MCP servers must have **external ingress** on ACA because Azure AI Foundry Agent Service calls them directly from Azure cloud. The MCP endpoint is `/mcp`.

Tool responses must complete in **<50 seconds** (Foundry non-streaming timeout).

## Azure AI Foundry V2 Integration

Agents are created via `AzureAIProjectAgentProvider`:

```python
provider = AzureAIProjectAgentProvider(ai_client=ai_client)
agent = await provider.create_agent(
    name="ContentPlanner",
    instructions="...",
    model="gpt-4o",
    tools=[bing_tool],
)
```

MCP tools are registered with:

```python
mcp_tool = ai_client.agents.get_mcp_tool(
    name="pptx-tools",
    url="https://pptx-mcp.<env>.azurecontainerapps.io/mcp",
    approval_mode="never_require",
    allowed_tools=["create_presentation", "add_slide", ...],
)
```

## Key Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| MCP transport | HTTP (stateless) | Required for Foundry to call externally |
| ACA ingress for MCP | External | Foundry calls from Azure cloud |
| ACA ingress for Orchestrator | Internal | Only bot needs it, no public exposure |
| Agent framework | agent-framework V2 (1.0.0rc2) | Native Foundry V2 CRUD agent support |
| Bot SDK | M365 Agents SDK (aiohttp) | Supports Teams + DirectLine natively |
| File format | PPTX (python-pptx) | Industry standard, full programmatic control |
| Storage | Azure Blob Storage | SAS URLs, scalable, no shared state |
| Language | English only | Simplified content pipeline |

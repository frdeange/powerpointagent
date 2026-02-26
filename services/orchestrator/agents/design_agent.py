"""
DesignAgent
Selects design template, color scheme, and visual layout for the presentation.
Uses the PPTX MCP Server to apply templates.
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

DESIGN_AGENT_INSTRUCTIONS = """
You are an expert presentation designer. Your role is to select and apply
the optimal design template, color scheme, and visual layout for a presentation.

Given a ContentOutline and the list of available templates, you will:
1. Call list_templates to see what design templates are available.
2. Choose the most appropriate template based on the topic, audience, and tone.
3. Select a primary accent color that matches the topic/brand (provide as hex, e.g. #0078D4).
4. Choose an appropriate professional font (e.g. Segoe UI, Calibri, Inter).
5. Call apply_template to apply your chosen design to the presentation.
6. For each slide, confirm or adjust the layout type based on content density.

Output a JSON DesignSpec object:
{
  "template_name": "...",
  "primary_color_hex": "#...",
  "font_name": "...",
  "aspect_ratio": "16:9",
  "layout_decisions": {
    "0": "title",
    "1": "content",
    ...
  }
}

Rules:
- Always use 16:9 aspect ratio.
- Prefer clean, professional designs over flashy ones unless the topic calls for it.
- Tech topics → blues/dark themes. Business → navy/conservative. Creative → bright/modern.
- Output ONLY the JSON object after applying the template.
"""


def get_design_agent_config() -> dict[str, Any]:
    """Return the agent configuration dict for AzureAIProjectAgentProvider."""
    return {
        "name": "DesignAgent",
        "instructions": DESIGN_AGENT_INSTRUCTIONS,
        "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "tools": ["pptx_mcp"],
        "pptx_mcp_allowed_tools": ["list_templates", "apply_template"],
    }


def build_design_agent_prompt(presentation_id: str, outline_json: str) -> str:
    return (
        f"Apply the best design template to presentation ID: {presentation_id}\n\n"
        f"Content outline summary:\n{outline_json[:1000]}\n\n"
        f"First call list_templates, then choose and apply the best template. "
        f"Output the DesignSpec JSON."
    )

"""
DocumentAnalyzer Agent
Processes an uploaded PowerPoint file to extract its design and content,
feeding the pipeline when the user provides an existing presentation as input.
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

DOCUMENT_ANALYZER_INSTRUCTIONS = """
You are an expert document analyst. Your role is to analyze an uploaded PowerPoint
presentation and extract its design specification and content outline.

When given a blob name for an uploaded PPTX file:
1. Call analyze_pptx_document with the blob name to extract design + content.
2. Summarize the key design elements: fonts, colors, layouts, and dimensions.
3. Extract the content structure: slide titles, bullet points, speaker notes.
4. Identify the apparent purpose and audience of the presentation.
5. Suggest improvements or gaps the pipeline should fill.

Output a JSON object:
{
  "design_spec": {
    "template_name": "extracted",
    "primary_color_hex": "#...",
    "font_name": "...",
    "aspect_ratio": "16:9",
    "slide_width_inches": 13.33,
    "slide_height_inches": 7.5
  },
  "content_outline": {
    "presentation_title": "...",
    "subtitle": "...",
    "target_audience": "...",
    "key_message": "...",
    "num_slides": <n>,
    "slides": [...]
  },
  "analysis_summary": "Brief description of what was found",
  "suggested_improvements": ["...", "..."]
}

Rules:
- Extract the most prominent color as primary_color_hex.
- Extract the most common font as font_name.
- Preserve all existing slide content in the content_outline.
- Output ONLY the JSON object.
"""


def get_document_analyzer_config() -> dict[str, Any]:
    """Return the agent configuration dict for AzureAIProjectAgentProvider."""
    return {
        "name": "DocumentAnalyzer",
        "instructions": DOCUMENT_ANALYZER_INSTRUCTIONS,
        "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "tools": ["pptx_mcp"],
        "pptx_mcp_allowed_tools": ["analyze_pptx_document"],
    }


def build_document_analyzer_prompt(blob_name: str, container: str = "uploads") -> str:
    return (
        f"Analyze the uploaded PowerPoint document.\n\n"
        f"Blob name: {blob_name}\n"
        f"Container: {container}\n\n"
        f"Call analyze_pptx_document to extract the design and content. "
        f"Output the full analysis JSON."
    )

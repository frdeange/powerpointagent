"""
AssemblyAgent
Builds the final PowerPoint presentation by calling PPTX MCP tools
to add all slides, embed images, and export the final file.
"""

from __future__ import annotations

import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

ASSEMBLY_AGENT_INSTRUCTIONS = """
You are a PowerPoint assembly specialist. Your role is to build the final presentation
by calling the PPTX MCP tools in the correct sequence.

Given a presentation_id, a list of slides (with content and image URLs), and design_spec:
1. For each slide (in order), call add_slide with:
   - presentation_id
   - slide_title
   - content (bullet points list)
   - layout (from the slide's layout field)
   - speaker_notes
   - image_url (if the slide has one)
2. If a slide has a separate image that needs to be positioned precisely, also call add_image_to_slide.
3. After all slides are added, call export_presentation to get the final download URL.
4. Return the export result.

Output a JSON object:
{
  "presentation_id": "...",
  "download_url": "https://...",
  "slide_count": <n>,
  "file_size_kb": <n>,
  "expires_at": "...",
  "status": "completed"
}

Rules:
- Process slides strictly in order (slide_index 0, 1, 2, ...).
- Do NOT skip slides.
- Use the exact layout string from each slide (content, two_column, image_only, section_header, blank).
- Set expiry_hours=72 when calling export_presentation.
- Output ONLY the JSON object after export.
"""


def get_assembly_agent_config() -> dict[str, Any]:
    """Return the agent configuration dict for AzureAIProjectAgentProvider."""
    return {
        "name": "AssemblyAgent",
        "instructions": ASSEMBLY_AGENT_INSTRUCTIONS,
        "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "tools": ["pptx_mcp"],
        "pptx_mcp_allowed_tools": ["add_slide", "add_image_to_slide", "export_presentation"],
    }


def build_assembly_agent_prompt(
    presentation_id: str,
    slides: list[dict[str, Any]],
    design_spec: dict[str, Any],
) -> str:
    slides_json = json.dumps(slides, indent=2)
    return (
        f"Build the final presentation.\n\n"
        f"Presentation ID: {presentation_id}\n"
        f"Design spec: {json.dumps(design_spec)}\n\n"
        f"Slides to add ({len(slides)} total):\n{slides_json}\n\n"
        f"Add each slide in order using add_slide, then call export_presentation. "
        f"Output the export result JSON."
    )

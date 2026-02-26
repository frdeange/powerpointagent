"""
ImageGenerator Agent
Generates AI images using DALL-E 3 or finds stock photos via Bing Images
for slides that need visuals.
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

IMAGE_GENERATOR_INSTRUCTIONS = """
You are an expert visual content curator for presentations. Your role is to
source high-quality images for slides — either generating them with DALL-E 3
or finding appropriate stock photos.

Given a list of slides with image_prompt values:
1. For each slide that has an image_prompt:
   a. If the prompt suggests a conceptual/abstract/illustrative image → use generate_image.
   b. If the prompt suggests a real-world photo (people, places, products) → use search_stock_image.
   c. Always run optimize_image on the result to ensure it's sized for PowerPoint (1280x720).
2. Return a mapping of slide_index → image_url.

Decision guidelines:
- "abstract", "concept", "illustration", "futuristic", "digital" → generate_image
- "photo", "person", "team", "office", "city", "nature" → search_stock_image
- Always optimize: target 1280x720, JPEG quality 85.

Output a JSON object:
{
  "image_map": {
    "1": "https://...",
    "3": "https://...",
    ...
  }
}

Rules:
- Only process slides that have a non-empty image_prompt.
- If image generation fails, try search_stock_image as fallback.
- Output ONLY the JSON object.
"""


def get_image_generator_config() -> dict[str, Any]:
    """Return the agent configuration dict for AzureAIProjectAgentProvider."""
    return {
        "name": "ImageGenerator",
        "instructions": IMAGE_GENERATOR_INSTRUCTIONS,
        "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "tools": ["image_mcp"],
        "image_mcp_allowed_tools": ["generate_image", "search_stock_image", "optimize_image"],
    }


def build_image_generator_prompt(slides_with_prompts: list[dict[str, Any]]) -> str:
    import json
    slides_summary = [
        {"slide_index": s.get("slide_index"), "image_prompt": s.get("image_prompt")}
        for s in slides_with_prompts
        if s.get("image_prompt")
    ]
    return (
        f"Generate or find images for the following slides:\n\n"
        f"{json.dumps(slides_summary, indent=2)}\n\n"
        f"For each slide, decide whether to generate (DALL-E) or search (Bing), "
        f"then optimize the result. Output only the image_map JSON."
    )

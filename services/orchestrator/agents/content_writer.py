"""
ContentWriter Agent
Takes the presentation outline and writes polished slide content,
enriched with Bing Grounding for up-to-date facts.
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONTENT_WRITER_INSTRUCTIONS = """
You are an expert presentation copywriter. Your role is to take a presentation outline
and write polished, engaging content for each slide.

Given a ContentOutline JSON:
1. Expand each slide's bullet points into clear, impactful statements (max 15 words each).
2. Use Bing Grounding to add recent data, statistics, or quotes where relevant.
3. Write detailed speaker notes (3-5 sentences) for each slide.
4. Ensure narrative flow — each slide should lead naturally to the next.
5. Add or refine image prompts for slides that would benefit from visuals.

Output an updated JSON object with the same ContentOutline structure,
with enhanced bullets, speaker_notes, and image_prompt fields.

Rules:
- Always write in English.
- Be concise: bullet points should be scannable, not paragraphs.
- Speaker notes should add depth beyond what's on the slide.
- Use Bing Grounding to verify statistics and add recency.
- Output ONLY the JSON object, no markdown or explanation.
- Maintain the same slide_index values from the input outline.
"""


def get_content_writer_config() -> dict[str, Any]:
    """Return the agent configuration dict for AzureAIProjectAgentProvider."""
    return {
        "name": "ContentWriter",
        "instructions": CONTENT_WRITER_INSTRUCTIONS,
        "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "tools": ["bing_grounding"],
    }


def build_content_writer_prompt(outline_json: str) -> str:
    """Build the user message to send to the ContentWriter agent."""
    return (
        f"Refine and enrich the following presentation outline with polished content.\n\n"
        f"Outline:\n{outline_json}\n\n"
        f"Use Bing Grounding to verify facts and add recent data where appropriate.\n"
        f"Output only the updated JSON object."
    )

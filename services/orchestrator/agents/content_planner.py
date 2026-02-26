"""
ContentPlanner Agent
Researches the topic using Bing Grounding and creates a structured presentation outline.
Registered in Azure AI Foundry V2 via AzureAIProjectAgentProvider.
"""

from __future__ import annotations

import json
import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

CONTENT_PLANNER_INSTRUCTIONS = """
You are an expert presentation strategist. Your role is to research a given topic
and create a compelling, structured outline for a professional PowerPoint presentation.

When given a user request:
1. Use Bing Grounding to research the topic, gather recent facts, statistics, and key insights.
2. Define the target audience, key message, and narrative arc.
3. Create a slide-by-slide outline with:
   - A clear title for each slide
   - 3-5 key bullet points per slide
   - Speaker notes with talking points
   - Suggested slide layouts (content, two_column, image_only, section_header)
   - Image suggestions where visual impact would enhance the message

Output a JSON object matching the ContentOutline schema:
{
  "presentation_title": "...",
  "subtitle": "...",
  "target_audience": "...",
  "key_message": "...",
  "num_slides": <number>,
  "slides": [
    {
      "slide_index": 0,
      "title": "...",
      "bullets": ["...", "..."],
      "speaker_notes": "...",
      "layout": "content|two_column|image_only|section_header|blank",
      "image_prompt": "..."
    }
  ]
}

Rules:
- Always write in English.
- Be concise and impactful — presentations should tell a story.
- First slide is always the title slide (layout: "title").
- Last slide is always a summary or call-to-action slide.
- Use Bing Grounding for factual claims and recent data.
- Output ONLY the JSON object, no markdown or explanation.
"""


def get_content_planner_config() -> dict[str, Any]:
    """Return the agent configuration dict for AzureAIProjectAgentProvider."""
    return {
        "name": "ContentPlanner",
        "instructions": CONTENT_PLANNER_INSTRUCTIONS,
        "model": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
        "tools": ["bing_grounding"],
    }


def build_content_planner_prompt(spec_dict: dict[str, Any]) -> str:
    """Build the user message to send to the ContentPlanner agent."""
    user_prompt = spec_dict.get("user_prompt", "")
    num_slides = (
        spec_dict.get("content_outline", {}).get("num_slides", 10)
        if spec_dict.get("content_outline")
        else 10
    )

    # If there's an uploaded document analysis, include it
    doc_analysis = spec_dict.get("_document_analysis", {})
    doc_context = ""
    if doc_analysis:
        existing_outline = doc_analysis.get("content_outline", [])
        doc_context = (
            f"\n\nThe user has uploaded an existing presentation with {len(existing_outline)} slides. "
            f"Use its content as a starting point and expand/improve upon it. "
            f"Existing slide titles: {[s.get('title', '') for s in existing_outline[:5]]}"
        )

    return (
        f"Create a presentation outline for the following request:\n\n"
        f"{user_prompt}\n\n"
        f"Target: {num_slides} slides.{doc_context}\n\n"
        f"Output only the JSON object."
    )

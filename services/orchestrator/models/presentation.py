"""
Pydantic models for presentation pipeline data flow.
All agents communicate using these typed structures.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PresentationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SlideLayout(str, Enum):
    TITLE = "title"
    CONTENT = "content"
    TWO_COLUMN = "two_column"
    IMAGE_ONLY = "image_only"
    SECTION_HEADER = "section_header"
    BLANK = "blank"


class SlideContent(BaseModel):
    slide_index: int = Field(0, description="0-based slide index")
    title: str = Field("", description="Slide title")
    bullets: list[str] = Field(default_factory=list, description="Bullet point content")
    speaker_notes: str = Field("", description="Speaker notes")
    layout: SlideLayout = Field(SlideLayout.CONTENT, description="Slide layout type")
    image_prompt: str = Field("", description="DALL-E prompt if an image should be generated")
    image_url: str = Field("", description="Final image URL (SAS or public)")


class DesignSpec(BaseModel):
    template_name: str = Field("default", description="Design template name")
    primary_color_hex: str = Field("", description="Primary accent color in hex (e.g. #0078D4)")
    font_name: str = Field("", description="Primary font name (e.g. Segoe UI)")
    aspect_ratio: str = Field("16:9", description="Slide aspect ratio")
    slide_width_inches: float = Field(13.33)
    slide_height_inches: float = Field(7.5)


class ContentOutline(BaseModel):
    presentation_title: str = Field("", description="Presentation title")
    subtitle: str = Field("", description="Subtitle or tagline")
    target_audience: str = Field("", description="Intended audience")
    key_message: str = Field("", description="Core message or call to action")
    slides: list[SlideContent] = Field(default_factory=list, description="Per-slide content")
    num_slides: int = Field(10, ge=3, le=50, description="Target number of slides")


class PresentationSpec(BaseModel):
    """
    Top-level specification passed through the entire pipeline.
    Created from the user request and optionally enriched by DocumentAnalyzer.
    """

    request_id: str = Field("", description="Unique request identifier")
    user_prompt: str = Field("", description="Original user request")
    language: str = Field("en", description="Content language (always 'en')")

    # Optional: set when user uploads a PPTX document
    uploaded_document_url: str = Field("", description="Blob URL of uploaded PPTX (optional)")
    uploaded_document_blob: str = Field("", description="Blob name in uploads container")

    # Filled by each agent in sequence
    content_outline: ContentOutline | None = Field(None, description="Filled by ContentPlanner")
    design_spec: DesignSpec | None = Field(None, description="Filled by DesignAgent or DocumentAnalyzer")
    slides: list[SlideContent] = Field(default_factory=list, description="Filled by ContentWriter")

    # Output
    presentation_id: str = Field("", description="PPTX blob ID (filled by AssemblyAgent)")
    download_url: str = Field("", description="Final SAS download URL")
    status: PresentationStatus = Field(PresentationStatus.PENDING)
    error: str = Field("", description="Error message if status=failed")

    # Metadata
    slide_count: int = Field(0)
    file_size_kb: float = Field(0.0)


class AgentResult(BaseModel):
    """Generic wrapper for agent output."""

    agent_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class UserRequest(BaseModel):
    """Incoming request from the bot service to the orchestrator."""

    user_id: str
    conversation_id: str
    message: str
    uploaded_document_url: str = ""
    uploaded_document_blob: str = ""
    num_slides: int = Field(10, ge=3, le=50)
    template_name: str = "default"
    language: str = "en"

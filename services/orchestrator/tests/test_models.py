"""
Tests for orchestrator models and workflow utilities.
"""

from __future__ import annotations

import json
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models.presentation import (
    PresentationSpec,
    PresentationStatus,
    ContentOutline,
    DesignSpec,
    SlideContent,
    SlideLayout,
    UserRequest,
    AgentResult,
)


# ── Tests: PresentationSpec ───────────────────────────────────────────────────

class TestPresentationSpec:
    def test_default_values(self):
        spec = PresentationSpec()
        assert spec.status == PresentationStatus.PENDING
        assert spec.language == "en"
        assert spec.slides == []
        assert spec.download_url == ""

    def test_with_user_prompt(self):
        spec = PresentationSpec(user_prompt="Create a deck about Azure AI")
        assert spec.user_prompt == "Create a deck about Azure AI"

    def test_serializes_to_json(self):
        spec = PresentationSpec(user_prompt="Test", request_id="req-001")
        data = json.loads(spec.model_dump_json())
        assert data["request_id"] == "req-001"
        assert data["user_prompt"] == "Test"
        assert data["status"] == "pending"

    def test_with_uploaded_document(self):
        spec = PresentationSpec(
            uploaded_document_blob="abc123.pptx",
            uploaded_document_url="https://storage.example.com/uploads/abc123.pptx",
        )
        assert spec.uploaded_document_blob == "abc123.pptx"


# ── Tests: ContentOutline ─────────────────────────────────────────────────────

class TestContentOutline:
    def test_default_num_slides(self):
        outline = ContentOutline()
        assert outline.num_slides == 10

    def test_slide_count_limits(self):
        with pytest.raises(Exception):
            ContentOutline(num_slides=2)  # min is 3
        with pytest.raises(Exception):
            ContentOutline(num_slides=51)  # max is 50

    def test_with_slides(self):
        outline = ContentOutline(
            presentation_title="AI in Healthcare",
            subtitle="Transforming Patient Care",
            slides=[
                SlideContent(slide_index=0, title="Introduction", bullets=["Point 1", "Point 2"]),
                SlideContent(slide_index=1, title="Key Findings", bullets=["Finding 1"]),
            ],
        )
        assert len(outline.slides) == 2
        assert outline.slides[0].title == "Introduction"


# ── Tests: SlideContent ───────────────────────────────────────────────────────

class TestSlideContent:
    def test_default_layout(self):
        slide = SlideContent()
        assert slide.layout == SlideLayout.CONTENT

    def test_all_fields(self):
        slide = SlideContent(
            slide_index=3,
            title="Technology Stack",
            bullets=["Azure AI Foundry", "FastMCP", "python-pptx"],
            speaker_notes="Discuss each technology briefly.",
            layout=SlideLayout.TWO_COLUMN,
            image_prompt="A futuristic data center",
            image_url="https://example.com/img.jpg",
        )
        assert slide.slide_index == 3
        assert len(slide.bullets) == 3
        assert slide.layout == SlideLayout.TWO_COLUMN
        assert slide.image_prompt == "A futuristic data center"


# ── Tests: DesignSpec ─────────────────────────────────────────────────────────

class TestDesignSpec:
    def test_default_values(self):
        ds = DesignSpec()
        assert ds.template_name == "default"
        assert ds.aspect_ratio == "16:9"
        assert ds.slide_width_inches == pytest.approx(13.33)

    def test_custom_color(self):
        ds = DesignSpec(primary_color_hex="#0078D4", font_name="Segoe UI")
        assert ds.primary_color_hex == "#0078D4"
        assert ds.font_name == "Segoe UI"


# ── Tests: UserRequest ────────────────────────────────────────────────────────

class TestUserRequest:
    def test_required_fields(self):
        req = UserRequest(
            user_id="user-123",
            conversation_id="conv-456",
            message="Create a 10-slide Azure AI presentation",
        )
        assert req.user_id == "user-123"
        assert req.language == "en"

    def test_num_slides_limits(self):
        with pytest.raises(Exception):
            UserRequest(user_id="u", conversation_id="c", message="test", num_slides=2)

    def test_with_upload(self):
        req = UserRequest(
            user_id="u",
            conversation_id="c",
            message="Improve this deck",
            uploaded_document_blob="upload.pptx",
        )
        assert req.uploaded_document_blob == "upload.pptx"


# ── Tests: workflow JSON parser ───────────────────────────────────────────────

class TestWorkflowJsonParser:
    def test_parse_clean_json(self):
        from orchestration.workflow import _parse_json

        data = _parse_json('{"key": "value", "num": 42}')
        assert data["key"] == "value"
        assert data["num"] == 42

    def test_parse_markdown_wrapped_json(self):
        from orchestration.workflow import _parse_json

        text = '```json\n{"presentation_title": "Test", "num_slides": 10}\n```'
        data = _parse_json(text)
        assert data["presentation_title"] == "Test"

    def test_parse_json_embedded_in_text(self):
        from orchestration.workflow import _parse_json

        text = 'Here is the result:\n{"status": "ok"}\nDone.'
        data = _parse_json(text)
        assert data["status"] == "ok"

    def test_returns_empty_on_invalid(self):
        from orchestration.workflow import _parse_json

        data = _parse_json("This is just plain text with no JSON")
        assert data == {}

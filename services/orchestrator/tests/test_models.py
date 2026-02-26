"""
Tests for orchestrator models and YAML agent definitions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

import sys

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
                SlideContent(
                    slide_index=0, title="Introduction", bullets=["Point 1", "Point 2"]
                ),
                SlideContent(
                    slide_index=1, title="Key Findings", bullets=["Finding 1"]
                ),
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


# ── Tests: YAML Agent Definitions ─────────────────────────────────────────────

AGENTS_DIR = Path(__file__).parent.parent / "agents"

EXPECTED_AGENTS = [
    "content_planner.yaml",
    "content_writer.yaml",
    "design_agent.yaml",
    "image_generator.yaml",
    "document_analyzer.yaml",
    "assembly_agent.yaml",
]

VALID_TOOL_KINDS = {"web_search", "mcp", "file_search", "code_interpreter", "function", "openapi", "custom"}


class TestYamlAgentDefinitions:
    """Validate that all YAML agent definitions are well-formed."""

    def test_all_yamls_exist(self):
        for filename in EXPECTED_AGENTS:
            path = AGENTS_DIR / filename
            assert path.exists(), f"Missing YAML agent definition: {path}"

    @pytest.mark.parametrize("filename", EXPECTED_AGENTS)
    def test_yaml_is_valid(self, filename):
        path = AGENTS_DIR / filename
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict), f"{filename} did not parse to a dict"

    @pytest.mark.parametrize("filename", EXPECTED_AGENTS)
    def test_yaml_has_required_fields(self, filename):
        path = AGENTS_DIR / filename
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data.get("kind") == "Prompt", f"{filename}: kind must be 'Prompt'"
        assert "name" in data, f"{filename}: missing 'name'"
        assert "instructions" in data, f"{filename}: missing 'instructions'"
        assert "model" in data, f"{filename}: missing 'model'"
        model = data["model"]
        assert "id" in model, f"{filename}: model missing 'id'"
        assert model.get("provider") == "AzureAI.ProjectProvider", (
            f"{filename}: model.provider must be 'AzureAI.ProjectProvider'"
        )

    @pytest.mark.parametrize("filename", EXPECTED_AGENTS)
    def test_yaml_tools_are_valid(self, filename):
        path = AGENTS_DIR / filename
        with open(path) as f:
            data = yaml.safe_load(f)
        tools = data.get("tools", [])
        for i, tool in enumerate(tools):
            kind = tool.get("kind")
            assert kind in VALID_TOOL_KINDS, (
                f"{filename}: tool[{i}] has invalid kind '{kind}'"
            )
            if kind == "mcp":
                assert "url" in tool, f"{filename}: MCP tool[{i}] missing 'url'"
                assert "allowedTools" in tool, (
                    f"{filename}: MCP tool[{i}] missing 'allowedTools'"
                )

    def test_content_planner_uses_web_search(self):
        with open(AGENTS_DIR / "content_planner.yaml") as f:
            data = yaml.safe_load(f)
        tool_kinds = [t["kind"] for t in data.get("tools", [])]
        assert "web_search" in tool_kinds

    def test_content_writer_uses_web_search(self):
        with open(AGENTS_DIR / "content_writer.yaml") as f:
            data = yaml.safe_load(f)
        tool_kinds = [t["kind"] for t in data.get("tools", [])]
        assert "web_search" in tool_kinds

    def test_design_agent_uses_mcp(self):
        with open(AGENTS_DIR / "design_agent.yaml") as f:
            data = yaml.safe_load(f)
        mcp_tools = [t for t in data.get("tools", []) if t["kind"] == "mcp"]
        assert len(mcp_tools) == 1
        assert "create_presentation" in mcp_tools[0]["allowedTools"]

    def test_assembly_agent_uses_mcp(self):
        with open(AGENTS_DIR / "assembly_agent.yaml") as f:
            data = yaml.safe_load(f)
        mcp_tools = [t for t in data.get("tools", []) if t["kind"] == "mcp"]
        assert len(mcp_tools) == 1
        assert "add_slide" in mcp_tools[0]["allowedTools"]
        assert "save_and_upload_presentation" in mcp_tools[0]["allowedTools"]

    def test_document_analyzer_has_analyze_tool(self):
        with open(AGENTS_DIR / "document_analyzer.yaml") as f:
            data = yaml.safe_load(f)
        mcp_tools = [t for t in data.get("tools", []) if t["kind"] == "mcp"]
        assert len(mcp_tools) == 1
        assert "analyze_pptx_document" in mcp_tools[0]["allowedTools"]

    def test_image_generator_uses_image_mcp(self):
        with open(AGENTS_DIR / "image_generator.yaml") as f:
            data = yaml.safe_load(f)
        mcp_tools = [t for t in data.get("tools", []) if t["kind"] == "mcp"]
        assert len(mcp_tools) == 1
        assert "generate_image" in mcp_tools[0]["allowedTools"]

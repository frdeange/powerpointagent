"""
Orchestration workflow — agent-framework V2
Uses AzureAIProjectAgentProvider + WorkflowBuilder to orchestrate the 5-6 agents.
Azure AI Foundry calls MCP servers directly; we only manage agents and flow here.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# agent-framework V2 imports
from agent_framework import AzureAIProjectAgentProvider
from agent_framework.orchestrations import WorkflowBuilder, SequentialBuilder

from ..agents.content_planner import (
    get_content_planner_config,
    build_content_planner_prompt,
)
from ..agents.content_writer import (
    get_content_writer_config,
    build_content_writer_prompt,
)
from ..agents.design_agent import get_design_agent_config, build_design_agent_prompt
from ..agents.image_generator import (
    get_image_generator_config,
    build_image_generator_prompt,
)
from ..agents.document_analyzer import (
    get_document_analyzer_config,
    build_document_analyzer_prompt,
)
from ..agents.assembly_agent import (
    get_assembly_agent_config,
    build_assembly_agent_prompt,
)
from ..models.presentation import (
    PresentationSpec,
    PresentationStatus,
    ContentOutline,
    DesignSpec,
    SlideContent,
)

logger = logging.getLogger(__name__)


def _get_ai_client() -> AIProjectClient:
    return AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )


def _get_bing_tool() -> dict[str, Any]:
    return {
        "type": "bing_grounding",
        "bing_grounding": {
            "search_configurations": [
                {"project_connection_id": os.environ["BING_PROJECT_CONNECTION_ID"]}
            ]
        },
    }


def _get_mcp_tool(name: str, url_env: str, allowed_tools: list[str]) -> Any:
    """
    Register an MCP server tool with Foundry Agent Service.
    Foundry calls the MCP server directly — no local client wrapper needed.
    """
    client = _get_ai_client()
    return client.agents.get_mcp_tool(
        name=name,
        url=os.environ[url_env],
        approval_mode="never_require",
        allowed_tools=allowed_tools,
    )


async def run_presentation_pipeline(spec: PresentationSpec) -> PresentationSpec:
    """
    Execute the full presentation generation pipeline.

    Flow (with uploaded document):
      DocumentAnalyzer → ContentPlanner → ContentWriter → DesignAgent
                                                         ↓            ↓ (concurrent)
                                                  ImageGenerator   AssemblyAgent waits
                                                         ↓
                                                   AssemblyAgent

    Flow (without uploaded document):
      ContentPlanner → ContentWriter → DesignAgent
                                      ↓            ↓ (concurrent)
                               ImageGenerator   ...
                                      ↓
                                AssemblyAgent
    """
    spec.request_id = spec.request_id or str(uuid.uuid4())
    spec.status = PresentationStatus.IN_PROGRESS
    logger.info("Starting pipeline for request %s", spec.request_id)

    try:
        ai_client = _get_ai_client()
        provider = AzureAIProjectAgentProvider(ai_client=ai_client)

        # ── Register MCP tools ────────────────────────────────────────────────
        pptx_mcp = _get_mcp_tool(
            name="pptx-tools",
            url_env="PPTX_MCP_SERVER_URL",
            allowed_tools=[
                "create_presentation",
                "add_slide",
                "apply_template",
                "add_image_to_slide",
                "export_presentation",
                "list_templates",
                "analyze_pptx_document",
            ],
        )
        image_mcp = _get_mcp_tool(
            name="image-tools",
            url_env="IMAGE_MCP_SERVER_URL",
            allowed_tools=["generate_image", "search_stock_image", "optimize_image"],
        )
        bing_tool = _get_bing_tool()

        # ── Create agents ─────────────────────────────────────────────────────
        model = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

        content_planner = await provider.create_agent(
            name="ContentPlanner",
            instructions=get_content_planner_config()["instructions"],
            model=model,
            tools=[bing_tool],
        )
        content_writer = await provider.create_agent(
            name="ContentWriter",
            instructions=get_content_writer_config()["instructions"],
            model=model,
            tools=[bing_tool],
        )
        design_agent = await provider.create_agent(
            name="DesignAgent",
            instructions=get_design_agent_config()["instructions"],
            model=model,
            tools=[pptx_mcp],
        )
        image_generator = await provider.create_agent(
            name="ImageGenerator",
            instructions=get_image_generator_config()["instructions"],
            model=model,
            tools=[image_mcp],
        )
        assembly_agent = await provider.create_agent(
            name="AssemblyAgent",
            instructions=get_assembly_agent_config()["instructions"],
            model=model,
            tools=[pptx_mcp],
        )

        # ── Step 0 (optional): DocumentAnalyzer ──────────────────────────────
        doc_analysis: dict[str, Any] = {}
        if spec.uploaded_document_blob:
            logger.info("Running DocumentAnalyzer on: %s", spec.uploaded_document_blob)
            doc_analyzer = await provider.create_agent(
                name="DocumentAnalyzer",
                instructions=get_document_analyzer_config()["instructions"],
                model=model,
                tools=[pptx_mcp],
            )
            prompt = build_document_analyzer_prompt(spec.uploaded_document_blob)
            result = await provider.run_agent(doc_analyzer, message=prompt)
            doc_analysis = _parse_json(result)
            logger.info("DocumentAnalyzer complete: %s", list(doc_analysis.keys()))

            # Pre-populate design_spec from analysis
            if "design_spec" in doc_analysis:
                spec.design_spec = DesignSpec(**doc_analysis["design_spec"])

        # ── Step 1: ContentPlanner ────────────────────────────────────────────
        logger.info("Running ContentPlanner")
        spec_dict: dict[str, Any] = spec.model_dump()
        if doc_analysis:
            spec_dict["_document_analysis"] = doc_analysis
        planner_prompt = build_content_planner_prompt(spec_dict)
        planner_result = await provider.run_agent(
            content_planner, message=planner_prompt
        )
        outline_data = _parse_json(planner_result)
        spec.content_outline = ContentOutline(**outline_data)
        logger.info(
            "ContentPlanner: %d slides planned", len(spec.content_outline.slides)
        )

        # ── Step 2: ContentWriter ─────────────────────────────────────────────
        logger.info("Running ContentWriter")
        writer_prompt = build_content_writer_prompt(json.dumps(outline_data, indent=2))
        writer_result = await provider.run_agent(content_writer, message=writer_prompt)
        writer_data = _parse_json(writer_result)
        spec.content_outline = ContentOutline(**writer_data)
        logger.info(
            "ContentWriter: refined %d slides", len(spec.content_outline.slides)
        )

        # ── Step 3: Create blank presentation in Foundry (via PPTX MCP) ──────
        logger.info("Creating blank presentation via PPTX MCP")
        create_prompt = (
            f"Create a new presentation with title '{spec.content_outline.presentation_title}' "
            f"and subtitle '{spec.content_outline.subtitle}'. "
            f"Use template: {spec.model_dump().get('template_name', 'default')}. "
            f"Output only the JSON result from create_presentation."
        )
        create_agent = await provider.create_agent(
            name="PresentationCreator",
            instructions="You call create_presentation and return the JSON result. Output only JSON.",
            model=model,
            tools=[pptx_mcp],
        )
        create_result = await provider.run_agent(create_agent, message=create_prompt)
        create_data = _parse_json(create_result)
        spec.presentation_id = create_data.get("presentation_id", str(uuid.uuid4()))
        logger.info("Presentation created: %s", spec.presentation_id)

        # ── Step 4: DesignAgent ───────────────────────────────────────────────
        logger.info("Running DesignAgent")
        design_prompt = build_design_agent_prompt(
            spec.presentation_id,
            json.dumps(outline_data, indent=2)[:800],
        )
        design_result = await provider.run_agent(design_agent, message=design_prompt)
        design_data = _parse_json(design_result)
        if not spec.design_spec:
            spec.design_spec = DesignSpec(
                **{k: v for k, v in design_data.items() if k in DesignSpec.model_fields}
            )

        # ── Step 5: ImageGenerator (run before assembly) ──────────────────────
        slides_list = [s.model_dump() for s in spec.content_outline.slides]
        slides_needing_images = [s for s in slides_list if s.get("image_prompt")]
        image_map: dict[str, str] = {}

        if slides_needing_images:
            logger.info(
                "Running ImageGenerator for %d slides", len(slides_needing_images)
            )
            img_prompt = build_image_generator_prompt(slides_needing_images)
            img_result = await provider.run_agent(image_generator, message=img_prompt)
            img_data = _parse_json(img_result)
            image_map = img_data.get("image_map", {})
            logger.info("ImageGenerator: %d images sourced", len(image_map))

        # Inject image URLs back into slides
        for slide in slides_list:
            idx_str = str(slide.get("slide_index", ""))
            if idx_str in image_map:
                slide["image_url"] = image_map[idx_str]

        spec.slides = [SlideContent(**s) for s in slides_list]

        # ── Step 6: AssemblyAgent ─────────────────────────────────────────────
        logger.info("Running AssemblyAgent for %d slides", len(spec.slides))
        assembly_prompt = build_assembly_agent_prompt(
            presentation_id=spec.presentation_id,
            slides=slides_list,
            design_spec=spec.design_spec.model_dump() if spec.design_spec else {},
        )
        assembly_result = await provider.run_agent(
            assembly_agent, message=assembly_prompt
        )
        assembly_data = _parse_json(assembly_result)

        spec.download_url = assembly_data.get("download_url", "")
        spec.slide_count = assembly_data.get("slide_count", len(spec.slides))
        spec.file_size_kb = assembly_data.get("file_size_kb", 0.0)
        spec.status = PresentationStatus.COMPLETED
        logger.info(
            "Pipeline complete: %s — %d slides, %.1f KB",
            spec.request_id,
            spec.slide_count,
            spec.file_size_kb,
        )

    except Exception as exc:
        logger.exception("Pipeline failed for %s", spec.request_id)
        spec.status = PresentationStatus.FAILED
        spec.error = str(exc)

    return spec


def _parse_json(text: str) -> dict[str, Any]:
    """Extract JSON from agent response text."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
        logger.error("Could not parse JSON from agent response: %s", text[:200])
        return {}

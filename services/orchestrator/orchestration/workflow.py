"""
Orchestration workflow — Declarative Agents + WorkflowBuilder

Pattern:
  - Agents defined in YAML (source of truth) in agents/ directory
  - Get-or-create: reuse existing agents in Foundry, create from YAML if missing
  - WorkflowBuilder: graph-based orchestration with fan-out/fan-in for parallelism
  - Azure AI Foundry calls MCP servers directly — no local wrappers

Flows:
  Standard:   ContentPlanner → ContentWriter → fan_out[DesignAgent, ImageGenerator] → fan_in → AssemblyAgent
  With doc:   DocumentAnalyzer → ContentPlanner → ContentWriter → fan_out[DesignAgent, ImageGenerator] → fan_in → AssemblyAgent
"""

from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import AzureCliCredential

from agent_framework import AgentExecutor, WorkflowBuilder
from agent_framework.azure import AzureAIProjectAgentProvider
from agent_framework_declarative import AgentFactory

logger = logging.getLogger(__name__)

# Directory containing the YAML agent definitions
AGENTS_DIR = Path(__file__).parent.parent / "agents"

# Agent names mapped to their YAML files
AGENT_YAMLS: dict[str, str] = {
    "ContentPlanner": "content_planner.yaml",
    "ContentWriter": "content_writer.yaml",
    "DesignAgent": "design_agent.yaml",
    "ImageGenerator": "image_generator.yaml",
    "DocumentAnalyzer": "document_analyzer.yaml",
    "AssemblyAgent": "assembly_agent.yaml",
}


async def get_or_create_from_yaml(
    provider: AzureAIProjectAgentProvider,
    factory: AgentFactory,
    name: str,
    yaml_path: Path,
) -> tuple:
    """Get an existing agent from Foundry, or create it from YAML if it doesn't exist.

    Returns:
        Tuple of (agent, was_created: bool)
    """
    try:
        agent = await provider.get_agent(name=name)
        logger.info("Agent '%s' retrieved from Foundry", name)
        return agent, False
    except ResourceNotFoundError:
        logger.info("Agent '%s' not found — creating from YAML: %s", name, yaml_path)
        agent = await factory.create_agent_from_yaml_path_async(str(yaml_path))
        return agent, True


async def run_presentation_pipeline(
    user_prompt: str,
    uploaded_document_url: str | None = None,
) -> dict:
    """
    Execute the full presentation generation pipeline.

    Args:
        user_prompt: The user's request (e.g. "10 slides about quantum computing").
        uploaded_document_url: Optional blob URL to an uploaded PPTX for analysis.

    Returns:
        Dict with outputs from each agent in the pipeline.
    """
    credential = AzureCliCredential()
    exit_stack = AsyncExitStack()

    try:
        endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
        model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

        # ── Initialize provider ───────────────────────────────────────────────
        provider = AzureAIProjectAgentProvider(
            credential=credential,
            project_endpoint=endpoint,
            model=model,
        )
        await exit_stack.enter_async_context(provider)

        factory = AgentFactory()

        # ── Determine which agents we need ────────────────────────────────────
        has_document = bool(uploaded_document_url)
        needed_agents = list(AGENT_YAMLS.keys())
        if not has_document:
            needed_agents.remove("DocumentAnalyzer")

        # ── Get-or-create all agents ──────────────────────────────────────────
        logger.info("Loading %d agents (get-or-create)...", len(needed_agents))
        agents: dict[str, object] = {}
        for name in needed_agents:
            yaml_path = AGENTS_DIR / AGENT_YAMLS[name]
            agent, was_created = await get_or_create_from_yaml(
                provider, factory, name, yaml_path
            )
            await exit_stack.enter_async_context(agent)
            agents[name] = agent
            status = "CREATED" if was_created else "RETRIEVED"
            logger.info("  • %s — %s", name, status)

        # ── Create executors ──────────────────────────────────────────────────
        executors = {name: AgentExecutor(agent) for name, agent in agents.items()}

        # ── Build workflow graph ──────────────────────────────────────────────
        planner_exec = executors["ContentPlanner"]
        writer_exec = executors["ContentWriter"]
        design_exec = executors["DesignAgent"]
        image_exec = executors["ImageGenerator"]
        assembly_exec = executors["AssemblyAgent"]

        if has_document:
            doc_exec = executors["DocumentAnalyzer"]
            workflow = (
                WorkflowBuilder(start_executor=doc_exec)
                .add_edge(doc_exec, planner_exec)
                .add_edge(planner_exec, writer_exec)
                .add_fan_out_edges(writer_exec, [design_exec, image_exec])
                .add_fan_in_edges([design_exec, image_exec], assembly_exec)
                .build()
            )
            # Prepend document URL to the user prompt
            prompt = (
                f"{user_prompt}\n\n"
                f"Reference document (analyze this first): {uploaded_document_url}"
            )
            logger.info(
                "Workflow built: DocumentAnalyzer → ContentPlanner → ContentWriter "
                "→ [DesignAgent ‖ ImageGenerator] → AssemblyAgent"
            )
        else:
            workflow = (
                WorkflowBuilder(start_executor=planner_exec)
                .add_edge(planner_exec, writer_exec)
                .add_fan_out_edges(writer_exec, [design_exec, image_exec])
                .add_fan_in_edges([design_exec, image_exec], assembly_exec)
                .build()
            )
            prompt = user_prompt
            logger.info(
                "Workflow built: ContentPlanner → ContentWriter "
                "→ [DesignAgent ‖ ImageGenerator] → AssemblyAgent"
            )

        # ── Execute ───────────────────────────────────────────────────────────
        logger.info("Executing workflow with prompt: %s", prompt[:100])
        result = await workflow.run(prompt)

        # ── Collect outputs ───────────────────────────────────────────────────
        outputs = result.get_outputs()
        pipeline_result = {
            "state": str(result.get_final_state()),
            "agent_outputs": [],
        }
        for output in outputs:
            author = "Unknown"
            if output.messages:
                author = getattr(output.messages[0], "author_name", None) or "Agent"
            pipeline_result["agent_outputs"].append(
                {"agent": author, "text": output.text}
            )

        logger.info("Pipeline complete — state: %s", pipeline_result["state"])
        return pipeline_result

    except Exception:
        logger.exception("Pipeline failed")
        raise
    finally:
        await exit_stack.aclose()
        await credential.close()

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "agent-framework-core",
#     "agent-framework-azure-ai",
#     "agent-framework-declarative",
#     "azure-identity",
#     "python-dotenv",
# ]
# ///
"""
Prueba: Agentes Declarativos con Patrón Get-or-Create + Workflow Secuencial

Este sample demuestra:
1. Agentes definidos en YAML (declarativos)
2. Patrón GET-OR-CREATE: primero intenta recuperar, si no existe crea desde YAML
3. Workflow secuencial: Researcher → Writer → Reviewer

Flujo:
- get_agent(name=X) → si existe, lo usa
- Si no existe → create_agent_from_yaml_path_async() lo crea

Beneficios:
- Definiciones de agentes en YAML (source of truth)
- No crea versiones duplicadas
- Usa 100% la biblioteca agent-framework
"""

import asyncio
import os
from contextlib import AsyncExitStack
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

from agent_framework import AgentExecutor, WorkflowBuilder
from agent_framework.azure import AzureAIProjectAgentProvider
from agent_framework_declarative import AgentFactory

# Load environment variables
load_dotenv()

# Directory containing YAML agent definitions
YAML_DIR = Path(__file__).parent


async def get_or_create_from_yaml(
    provider: AzureAIProjectAgentProvider,
    factory: AgentFactory,
    name: str,
    yaml_path: Path,
) -> tuple:
    """Get existing agent or create from YAML definition.
    
    Args:
        provider: The AzureAIProjectAgentProvider for get_agent
        factory: AgentFactory for creating from YAML
        name: Agent name to look up
        yaml_path: Path to YAML file if creation needed
    
    Returns:
        Tuple of (agent, was_created: bool)
    """
    try:
        agent = await provider.get_agent(name=name)
        return agent, False
    except ResourceNotFoundError:
        # Agent doesn't exist, create from YAML
        agent = await factory.create_agent_from_yaml_path_async(str(yaml_path))
        return agent, True


async def main() -> None:
    print("=" * 70)
    print("DEMO: Agentes Declarativos + Get-or-Create + Workflow")
    print("=" * 70)

    credential = AzureCliCredential()
    exit_stack = AsyncExitStack()
    
    try:
        # Get config from environment
        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT required")
        
        model = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
        
        # Create provider (for get_agent) - managed by exit stack
        provider = AzureAIProjectAgentProvider(
            credential=credential,
            project_endpoint=endpoint,
            model=model,
        )
        await exit_stack.enter_async_context(provider)
        
        # Create factory (for create from YAML)
        factory = AgentFactory()

        # === Agent YAML configs ===
        agent_yamls = [
            ("Researcher", YAML_DIR / "researcher.yaml"),
            ("Writer", YAML_DIR / "writer.yaml"),
            ("Reviewer", YAML_DIR / "reviewer.yaml"),
        ]

        # === Get or create agents ===
        print("\n[1] Cargando agentes (get-or-create)...")
        agents = []
        results = []
        for name, yaml_path in agent_yamls:
            print(f"    • {name}...", end=" ")
            agent, was_created = await get_or_create_from_yaml(
                provider, factory, name, yaml_path
            )
            # Enter agent into exit stack for proper MCP cleanup
            await exit_stack.enter_async_context(agent)
            agents.append(agent)
            results.append((name, was_created))
            status = "✓ CREATED" if was_created else "✓ RETRIEVED"
            print(status)

        # Summary
        new_count = sum(1 for _, created in results if created)
        existing_count = len(results) - new_count
        print(f"\n    → {existing_count} reutilizados, {new_count} nuevos")

        # Unpack agents
        researcher, writer, reviewer = agents

        # Create executors
        researcher_executor = AgentExecutor(researcher)
        writer_executor = AgentExecutor(writer)
        reviewer_executor = AgentExecutor(reviewer)

        # === Build sequential workflow ===
        print("\n[4] Construyendo workflow secuencial...")
        workflow = (
            WorkflowBuilder(start_executor=researcher_executor)
            .add_edge(researcher_executor, writer_executor)
            .add_edge(writer_executor, reviewer_executor)
            .build()
        )
        print("    ✓ Workflow: Researcher → Writer → Reviewer")

        # === Execute the workflow ===
        prompt = "What is Azure AI Agent Service and how do I create my first agent?"
        print(f"\n[5] Ejecutando workflow con prompt:")
        print(f"    '{prompt}'")
        print("\n" + "-" * 70)

        result = await workflow.run(prompt)

        # === Show results ===
        print("\n[6] Resultados del workflow:")
        print("-" * 70)
        outputs = result.get_outputs()
        for output in outputs:
            author = "Unknown"
            if output.messages:
                author = getattr(output.messages[0], "author_name", None) or "Agent"
            print(f"\n{'='*20} {author} {'='*20}")
            print(output.text)
        print("\n" + "-" * 70)

        print(f"\n✅ Workflow completado! Estado: {result.get_final_state()}")
        print("\nNota: Los agentes persisten en Azure AI Foundry.")
        print("      En la próxima ejecución, serán RETRIEVED (no creados de nuevo).")

    finally:
        # Close exit stack (closes provider, agents, and MCP sessions)
        await exit_stack.aclose()
        await credential.close()


if __name__ == "__main__":
    asyncio.run(main())

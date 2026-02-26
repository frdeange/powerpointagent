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
Prueba: Medición de Tiempos en Agentes Declarativos

Este script es idéntico a main.py pero con instrumentación de tiempos
para medir cuánto tarda cada operación.

Métricas capturadas:
- Inicialización del provider
- Get-or-create de cada agente (individual)
- Tiempo total de carga de agentes
- Construcción del workflow
- Ejecución del workflow
- Tiempo total
"""

import asyncio
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
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


@dataclass
class TimingResult:
    """Stores timing information for an operation."""
    name: str
    duration_ms: float
    details: str = ""


class Timer:
    """Simple context manager for timing operations."""
    
    def __init__(self, name: str, details: str = ""):
        self.name = name
        self.details = details
        self.start_time: float = 0
        self.duration_ms: float = 0
    
    def __enter__(self) -> "Timer":
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args) -> None:
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000


def format_duration(ms: float) -> str:
    """Format duration in human-readable format."""
    if ms < 1000:
        return f"{ms:.1f}ms"
    else:
        return f"{ms/1000:.2f}s"


async def get_or_create_from_yaml(
    provider: AzureAIProjectAgentProvider,
    factory: AgentFactory,
    name: str,
    yaml_path: Path,
) -> tuple:
    """Get existing agent or create from YAML definition.
    
    Returns:
        Tuple of (agent, was_created: bool, get_time_ms, create_time_ms)
    """
    get_time_ms = 0.0
    create_time_ms = 0.0
    
    # Time the get_agent call
    start = time.perf_counter()
    try:
        agent = await provider.get_agent(name=name)
        get_time_ms = (time.perf_counter() - start) * 1000
        return agent, False, get_time_ms, create_time_ms
    except ResourceNotFoundError:
        get_time_ms = (time.perf_counter() - start) * 1000
        
        # Time the create_agent call
        start = time.perf_counter()
        agent = await factory.create_agent_from_yaml_path_async(str(yaml_path))
        create_time_ms = (time.perf_counter() - start) * 1000
        return agent, True, get_time_ms, create_time_ms


async def main() -> None:
    print("=" * 70)
    print("DEMO: Agentes Declarativos + Get-or-Create + Workflow")
    print("⏱️  CON MEDICIÓN DE TIEMPOS")
    print("=" * 70)

    timings: list[TimingResult] = []
    total_start = time.perf_counter()
    
    credential = AzureCliCredential()
    exit_stack = AsyncExitStack()
    
    try:
        # Get config from environment
        endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
        if not endpoint:
            raise ValueError("AZURE_AI_PROJECT_ENDPOINT required")
        
        model = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
        
        # === Time: Provider initialization ===
        print("\n[1] Inicializando provider...")
        with Timer("Provider Init") as t:
            provider = AzureAIProjectAgentProvider(
                credential=credential,
                project_endpoint=endpoint,
                model=model,
            )
            await exit_stack.enter_async_context(provider)
        timings.append(TimingResult("Provider Init", t.duration_ms))
        print(f"    ✓ Provider listo ({format_duration(t.duration_ms)})")
        
        # Create factory (for create from YAML)
        factory = AgentFactory()

        # === Agent YAML configs ===
        agent_yamls = [
            ("Researcher", YAML_DIR / "researcher.yaml"),
            ("Writer", YAML_DIR / "writer.yaml"),
            ("Reviewer", YAML_DIR / "reviewer.yaml"),
        ]

        # === Time: Get or create agents (PARALLEL) ===
        print("\n[2] Cargando agentes (get-or-create) EN PARALELO...")
        agents_start = time.perf_counter()
        
        # Launch all get_or_create calls in parallel
        async def load_agent(name: str, yaml_path: Path):
            """Load a single agent and return timing info."""
            agent, was_created, get_ms, create_ms = await get_or_create_from_yaml(
                provider, factory, name, yaml_path
            )
            return name, agent, was_created, get_ms, create_ms
        
        # Execute all in parallel
        results = await asyncio.gather(*[
            load_agent(name, yaml_path) 
            for name, yaml_path in agent_yamls
        ])
        
        parallel_ms = (time.perf_counter() - agents_start) * 1000
        
        # Process results and enter contexts
        agents = []
        agent_results = []
        for name, agent, was_created, get_ms, create_ms in results:
            # Enter agent into exit stack for proper MCP cleanup
            with Timer("Enter Context") as ctx_timer:
                await exit_stack.enter_async_context(agent)
            
            agents.append(agent)
            
            if was_created:
                status = f"✓ CREATED (get: {format_duration(get_ms)}, create: {format_duration(create_ms)}, ctx: {format_duration(ctx_timer.duration_ms)})"
                total_agent_ms = get_ms + create_ms + ctx_timer.duration_ms
                timings.append(TimingResult(f"Agent: {name}", total_agent_ms, 
                    f"get={get_ms:.0f}ms, create={create_ms:.0f}ms, ctx={ctx_timer.duration_ms:.0f}ms"))
            else:
                status = f"✓ RETRIEVED (get: {format_duration(get_ms)}, ctx: {format_duration(ctx_timer.duration_ms)})"
                total_agent_ms = get_ms + ctx_timer.duration_ms
                timings.append(TimingResult(f"Agent: {name}", total_agent_ms,
                    f"get={get_ms:.0f}ms, ctx={ctx_timer.duration_ms:.0f}ms"))
            
            agent_results.append((name, was_created))
            print(f"    • {name}... {status}")

        agents_total_ms = (time.perf_counter() - agents_start) * 1000
        timings.append(TimingResult("Agents Total (parallel)", parallel_ms, "tiempo real con gather"))

        # Summary
        new_count = sum(1 for _, created in agent_results if created)
        existing_count = len(agent_results) - new_count
        print(f"\n    → {existing_count} reutilizados, {new_count} nuevos")
        print(f"    → Tiempo total agentes: {format_duration(agents_total_ms)}")

        # Unpack agents
        researcher, writer, reviewer = agents

        # Create executors
        researcher_executor = AgentExecutor(researcher)
        writer_executor = AgentExecutor(writer)
        reviewer_executor = AgentExecutor(reviewer)

        # === Time: Build workflow ===
        print("\n[3] Construyendo workflow secuencial...")
        with Timer("Workflow Build") as t:
            workflow = (
                WorkflowBuilder(start_executor=researcher_executor)
                .add_edge(researcher_executor, writer_executor)
                .add_edge(writer_executor, reviewer_executor)
                .build()
            )
        timings.append(TimingResult("Workflow Build", t.duration_ms))
        print(f"    ✓ Workflow: Researcher → Writer → Reviewer ({format_duration(t.duration_ms)})")

        # === Time: Execute workflow ===
        prompt = "What is Azure AI Agent Service and how do I create my first agent?"
        print(f"\n[4] Ejecutando workflow con prompt:")
        print(f"    '{prompt}'")
        print("\n" + "-" * 70)

        with Timer("Workflow Execution") as t:
            result = await workflow.run(prompt)
        timings.append(TimingResult("Workflow Execution", t.duration_ms))

        # === Show results ===
        print("\n[5] Resultados del workflow:")
        print("-" * 70)
        outputs = result.get_outputs()
        for output in outputs:
            author = "Unknown"
            if output.messages:
                author = getattr(output.messages[0], "author_name", None) or "Agent"
            print(f"\n{'='*20} {author} {'='*20}")
            # Show truncated output to focus on timing
            text = output.text
            if len(text) > 500:
                print(text[:500] + "...\n[truncado para ver tiempos]")
            else:
                print(text)
        print("\n" + "-" * 70)

        print(f"\n✅ Workflow completado! Estado: {result.get_final_state()}")

    finally:
        # === Time: Cleanup ===
        print("\n[6] Limpiando recursos...")
        with Timer("Cleanup") as t:
            await exit_stack.aclose()
            await credential.close()
        timings.append(TimingResult("Cleanup", t.duration_ms))
        print(f"    ✓ Recursos liberados ({format_duration(t.duration_ms)})")

    # === Timing Summary ===
    total_ms = (time.perf_counter() - total_start) * 1000
    
    print("\n" + "=" * 70)
    print("⏱️  RESUMEN DE TIEMPOS")
    print("=" * 70)
    print(f"\n{'Operación':<25} {'Tiempo':>12}   {'Detalles'}")
    print("-" * 70)
    
    for timing in timings:
        details = f"   ({timing.details})" if timing.details else ""
        print(f"{timing.name:<25} {format_duration(timing.duration_ms):>12}{details}")
    
    print("-" * 70)
    print(f"{'TOTAL':<25} {format_duration(total_ms):>12}")
    print("=" * 70)
    
    # Analysis
    print("\n📊 ANÁLISIS:")
    agents_ms = sum(t.duration_ms for t in timings if t.name.startswith("Agent:"))
    workflow_exec_ms = next((t.duration_ms for t in timings if t.name == "Workflow Execution"), 0)
    overhead_ms = total_ms - workflow_exec_ms
    
    print(f"   • Overhead (sin ejecución):  {format_duration(overhead_ms)} ({overhead_ms/total_ms*100:.1f}%)")
    print(f"   • Carga de agentes:          {format_duration(agents_ms)} ({agents_ms/total_ms*100:.1f}%)")
    print(f"   • Ejecución workflow:        {format_duration(workflow_exec_ms)} ({workflow_exec_ms/total_ms*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())

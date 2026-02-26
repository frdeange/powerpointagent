"""
Orchestrator Service — FastAPI
Receives presentation requests from the Bot Service and runs the agent pipeline.
Deployed as an internal ACA service (not publicly accessible).
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse

from azure.storage.blob import BlobServiceClient

from models.presentation import UserRequest, PresentationStatus
from orchestration.workflow import run_presentation_pipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Orchestrator starting up")
    yield
    logger.info("Orchestrator shutting down")


app = FastAPI(
    title="PowerPoint Agent Orchestrator",
    description="Multi-agent presentation generation service",
    version="1.0.0",
    lifespan=lifespan,
)

# In-memory job store (replace with Redis/Cosmos for production)
_jobs: dict[str, dict[str, Any]] = {}


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "orchestrator"})


@app.post("/generate")
async def generate_presentation(
    request: UserRequest,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    Start a presentation generation job.
    Returns immediately with a job_id for polling.
    """
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending"}

    background_tasks.add_task(
        _run_pipeline_task,
        job_id,
        request.message,
        request.uploaded_document_url or None,
    )

    logger.info("Job %s queued for user %s", job_id, request.user_id)
    return JSONResponse(
        {
            "job_id": job_id,
            "status": "pending",
            "message": "Generation started",
        }
    )


async def _run_pipeline_task(
    job_id: str,
    user_prompt: str,
    uploaded_document_url: str | None,
) -> None:
    """Background task: run the pipeline and update job store."""
    _jobs[job_id]["status"] = "in_progress"
    try:
        result = await run_presentation_pipeline(
            user_prompt=user_prompt,
            uploaded_document_url=uploaded_document_url,
        )
        _jobs[job_id] = {
            "status": "completed",
            "state": result.get("state", ""),
            "agent_outputs": result.get("agent_outputs", []),
        }
    except Exception as exc:
        logger.exception("Pipeline task failed for %s", job_id)
        _jobs[job_id] = {"status": "failed", "error": str(exc)}


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> JSONResponse:
    """Poll job status. Returns download_url when status='completed'."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(_jobs[job_id])


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user_id: str = Form(...),
) -> JSONResponse:
    """
    Upload a PPTX document for analysis.
    Stores it in the uploads blob container and returns the blob name.
    """
    if not file.filename or not file.filename.lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are supported")

    blob_name = f"{uuid.uuid4()}_{file.filename}"
    contents = await file.read()

    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    blob_client = BlobServiceClient.from_connection_string(conn_str)
    container = os.environ.get("BLOB_CONTAINER_UPLOADS", "uploads")
    blob = blob_client.get_blob_client(container=container, blob=blob_name)
    blob.upload_blob(contents, overwrite=True)

    logger.info("Uploaded document: %s (%d bytes)", blob_name, len(contents))
    return JSONResponse(
        {
            "blob_name": blob_name,
            "container": container,
            "file_size_bytes": len(contents),
            "status": "uploaded",
        }
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)

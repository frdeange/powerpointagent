"""
Frontend Service — Simple web UI for PowerPoint Agent.
Serves static HTML and proxies API calls to the orchestrator.
"""

import os
import logging

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ORCHESTRATOR_URL = os.environ.get(
    "ORCHESTRATOR_URL",
    "http://pptcreator-aca-orchestrator.internal.mangocoast-3452809f.swedencentral.azurecontainerapps.io",
)

app = FastAPI(title="PowerPoint Agent — Web UI")

# ── API proxy to orchestrator ─────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "frontend"}


@app.post("/api/generate")
async def generate(
    message: str = Form(...),
    num_slides: int = Form(10),
    template_name: str = Form("default"),
):
    """Proxy generation request to orchestrator."""
    payload = {
        "user_id": "web-user",
        "conversation_id": "web-session",
        "message": message,
        "num_slides": num_slides,
        "template_name": template_name,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{ORCHESTRATOR_URL}/generate", json=payload)
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    """Proxy job status poll to orchestrator."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{ORCHESTRATOR_URL}/jobs/{job_id}")
        return JSONResponse(resp.json(), status_code=resp.status_code)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """Proxy file upload to orchestrator."""
    async with httpx.AsyncClient(timeout=60) as client:
        files = {"file": (file.filename, await file.read(), file.content_type)}
        data = {"user_id": "web-user"}
        resp = await client.post(f"{ORCHESTRATOR_URL}/upload", files=files, data=data)
        return JSONResponse(resp.json(), status_code=resp.status_code)


# ── Serve static files (must be last) ────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "3000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)

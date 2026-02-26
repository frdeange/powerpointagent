"""
Image MCP Server — FastMCP 3.x
Exposes 3 tools: generate_image (DALL-E 3), search_stock_image (Bing Images), optimize_image.
Hosted on Azure Container Apps with external ingress.
Azure AI Foundry calls this server directly via AzureAIClient.get_mcp_tool().
"""

import os
import io
import uuid
import base64
import logging
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from PIL import Image

from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── FastMCP setup ─────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="image-mcp-server",
    instructions=(
        "Provides tools to generate AI images (DALL-E 3), search stock photos (Bing Images), "
        "and optimize/resize images for PowerPoint slides. "
        "All images are stored in Azure Blob Storage and returned as SAS URLs."
    ),
    stateless_http=True,
)

# ── Azure Storage ─────────────────────────────────────────────────────────────
_blob_client: BlobServiceClient | None = None


def get_blob_client() -> BlobServiceClient:
    global _blob_client
    if _blob_client is None:
        conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        _blob_client = BlobServiceClient.from_connection_string(conn_str)
    return _blob_client


CONTAINER_IMAGES = os.environ.get("BLOB_CONTAINER_IMAGES", "images")


def _upload_image(image_bytes: bytes, extension: str = "png") -> str:
    """Upload image to blob and return SAS URL."""
    blob_name = f"{uuid.uuid4()}.{extension}"
    client = get_blob_client()
    blob = client.get_blob_client(container=CONTAINER_IMAGES, blob=blob_name)
    blob.upload_blob(image_bytes, overwrite=True, content_settings={"content_type": f"image/{extension}"})

    account_key = client.credential.account_key
    sas = generate_blob_sas(
        account_name=client.account_name,
        container_name=CONTAINER_IMAGES,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(hours=72),
    )
    return f"https://{client.account_name}.blob.core.windows.net/{CONTAINER_IMAGES}/{blob_name}?{sas}"


# ── Tool 1: generate_image ────────────────────────────────────────────────────
@mcp.tool()
async def generate_image(
    prompt: str,
    size: str = "1792x1024",
    quality: str = "hd",
    style: str = "vivid",
) -> dict[str, Any]:
    """
    Generate an AI image using DALL-E 3 (Azure OpenAI).

    Args:
        prompt: Detailed description of the image to generate.
        size: Image dimensions — '1024x1024', '1792x1024' (landscape, default), or '1024x1792'.
        quality: 'standard' or 'hd' (default).
        style: 'vivid' (default, dramatic) or 'natural' (realistic).

    Returns:
        dict with image_url (SAS URL), revised_prompt, and metadata.
    """
    endpoint = os.environ.get("AZURE_OPENAI_DALLE_ENDPOINT", "")
    api_key = os.environ.get("AZURE_OPENAI_DALLE_API_KEY", "")
    deployment = os.environ.get("AZURE_OPENAI_DALLE_DEPLOYMENT", "dall-e-3")
    api_version = "2024-02-01"

    url = f"{endpoint}/openai/deployments/{deployment}/images/generations?api-version={api_version}"
    headers = {"api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "style": style,
        "response_format": "b64_json",
    }

    async with httpx.AsyncClient(timeout=50.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    image_b64 = data["data"][0]["b64_json"]
    revised_prompt = data["data"][0].get("revised_prompt", prompt)
    image_bytes = base64.b64decode(image_b64)

    # Store in blob
    image_url = _upload_image(image_bytes, "png")

    logger.info("Generated image: size=%s quality=%s", size, quality)
    return {
        "image_url": image_url,
        "revised_prompt": revised_prompt,
        "size": size,
        "quality": quality,
        "style": style,
        "status": "generated",
    }


# ── Tool 2: search_stock_image ────────────────────────────────────────────────
@mcp.tool()
async def search_stock_image(
    query: str,
    count: int = 5,
    safe_search: str = "Strict",
    aspect: str = "Wide",
) -> dict[str, Any]:
    """
    Search for stock photos using Bing Image Search API.

    Args:
        query: Search query describing the desired image.
        count: Number of results to return (1–10, default 5).
        safe_search: Content filter — 'Strict' (default), 'Moderate', or 'Off'.
        aspect: Image aspect ratio filter — 'Wide' (16:9, default), 'Square', 'Tall', 'All'.

    Returns:
        dict with list of images (thumbnail_url, content_url, name, width, height).
    """
    api_key = os.environ.get("BING_SEARCH_API_KEY", "")
    endpoint = os.environ.get("BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com")
    url = f"{endpoint}/v7.0/images/search"

    params = {
        "q": query,
        "count": min(count, 10),
        "safeSearch": safe_search,
        "aspect": aspect,
        "imageType": "Photo",
        "license": "Any",
    }
    headers = {"Ocp-Apim-Subscription-Key": api_key}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    images = []
    for item in data.get("value", []):
        images.append(
            {
                "name": item.get("name", ""),
                "thumbnail_url": item.get("thumbnailUrl", ""),
                "content_url": item.get("contentUrl", ""),
                "width": item.get("width", 0),
                "height": item.get("height", 0),
                "host_page_url": item.get("hostPageUrl", ""),
            }
        )

    logger.info("Stock image search '%s': %d results", query, len(images))
    return {
        "query": query,
        "images": images,
        "total_results": data.get("totalEstimatedMatches", 0),
        "status": "success",
    }


# ── Tool 3: optimize_image ─────────────────────────────────────────────────────
@mcp.tool()
async def optimize_image(
    image_url: str,
    target_width: int = 1280,
    target_height: int = 720,
    quality: int = 85,
    format: str = "JPEG",
) -> dict[str, Any]:
    """
    Download, resize, and compress an image for optimal PowerPoint embedding.

    Args:
        image_url: URL of the source image (public or SAS URL).
        target_width: Target width in pixels (default 1280).
        target_height: Target height in pixels (default 720).
        quality: JPEG/WebP compression quality 1–95 (default 85).
        format: Output format — 'JPEG' (default), 'PNG', or 'WEBP'.

    Returns:
        dict with optimized image_url, dimensions, and file_size_kb.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(image_url)
        resp.raise_for_status()
        original_bytes = resp.content

    img = Image.open(io.BytesIO(original_bytes)).convert("RGB")
    orig_w, orig_h = img.size

    # Maintain aspect ratio within target bounds
    img.thumbnail((target_width, target_height), Image.LANCZOS)
    final_w, final_h = img.size

    buf = io.BytesIO()
    fmt = format.upper()
    save_kwargs: dict[str, Any] = {"format": fmt}
    if fmt in ("JPEG", "WEBP"):
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    img.save(buf, **save_kwargs)
    optimized_bytes = buf.getvalue()

    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt, "jpg")
    optimized_url = _upload_image(optimized_bytes, ext)

    logger.info(
        "Optimized image: %dx%d → %dx%d (%.1f KB)",
        orig_w, orig_h, final_w, final_h, len(optimized_bytes) / 1024,
    )
    return {
        "image_url": optimized_url,
        "original_dimensions": {"width": orig_w, "height": orig_h},
        "optimized_dimensions": {"width": final_w, "height": final_h},
        "file_size_kb": round(len(optimized_bytes) / 1024, 1),
        "format": fmt,
        "status": "optimized",
    }


# ── Health check ──────────────────────────────────────────────────────────────
@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "image-mcp-server", "tools": 3})


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    mcp.run(transport="http", host="0.0.0.0", port=port)

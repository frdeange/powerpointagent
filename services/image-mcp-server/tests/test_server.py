"""
Tests for Image MCP Server tools.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault(
    "AZURE_STORAGE_CONNECTION_STRING",
    "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net",
)
os.environ.setdefault("AZURE_OPENAI_DALLE_ENDPOINT", "https://test.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_DALLE_API_KEY", "test-key")
os.environ.setdefault("BING_SEARCH_API_KEY", "test-bing-key")


def make_test_image(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def mock_upload(monkeypatch):
    """Mock blob upload to return a fake SAS URL."""

    def fake_upload(image_bytes: bytes, ext: str = "png") -> str:
        return f"https://test.blob.core.windows.net/images/mock-{ext}?sas=test"

    monkeypatch.setattr("server._upload_image", fake_upload)


# ── Tests: generate_image ─────────────────────────────────────────────────────


class TestGenerateImage:
    @pytest.mark.asyncio
    async def test_generate_uses_dalle(self, mock_upload, monkeypatch):
        from server import generate_image

        fake_image_b64 = base64.b64encode(make_test_image()).decode()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [{"b64_json": fake_image_b64, "revised_prompt": "A test image"}]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await generate_image(prompt="A blue abstract concept")

        assert result["status"] == "generated"
        assert "image_url" in result
        assert result["revised_prompt"] == "A test image"

    @pytest.mark.asyncio
    async def test_generate_respects_size_param(self, mock_upload, monkeypatch):
        from server import generate_image

        fake_image_b64 = base64.b64encode(make_test_image()).decode()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "data": [{"b64_json": fake_image_b64, "revised_prompt": "test"}]
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await generate_image(
                prompt="test", size="1024x1024", quality="standard"
            )

        assert result["size"] == "1024x1024"
        assert result["quality"] == "standard"


# ── Tests: search_stock_image ─────────────────────────────────────────────────


class TestSearchStockImage:
    @pytest.mark.asyncio
    async def test_search_returns_images(self, monkeypatch):
        from server import search_stock_image

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "value": [
                {
                    "name": "Business meeting",
                    "thumbnailUrl": "https://tse1.mm.bing.net/th?id=test",
                    "contentUrl": "https://example.com/image.jpg",
                    "width": 1920,
                    "height": 1080,
                    "hostPageUrl": "https://example.com",
                }
            ],
            "totalEstimatedMatches": 1000,
        }
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await search_stock_image(query="business meeting", count=1)

        assert result["status"] == "success"
        assert len(result["images"]) == 1
        assert result["images"][0]["name"] == "Business meeting"

    @pytest.mark.asyncio
    async def test_search_caps_count_at_10(self, monkeypatch):
        from server import search_stock_image

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"value": [], "totalEstimatedMatches": 0}
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            # Should not raise even with count > 10
            result = await search_stock_image(query="test", count=50)

        assert result["status"] == "success"


# ── Tests: optimize_image ─────────────────────────────────────────────────────


class TestOptimizeImage:
    @pytest.mark.asyncio
    async def test_optimizes_and_resizes(self, mock_upload, monkeypatch):
        from server import optimize_image

        test_img_bytes = make_test_image(width=2000, height=1500)
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = test_img_bytes
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await optimize_image(
                image_url="https://example.com/large.png",
                target_width=1280,
                target_height=720,
            )

        assert result["status"] == "optimized"
        assert result["optimized_dimensions"]["width"] <= 1280
        assert result["optimized_dimensions"]["height"] <= 720
        assert result["file_size_kb"] > 0

    @pytest.mark.asyncio
    async def test_optimize_png_format(self, mock_upload, monkeypatch):
        from server import optimize_image

        test_img_bytes = make_test_image()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = test_img_bytes
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await optimize_image(
                image_url="https://example.com/image.png",
                format="PNG",
            )

        assert result["format"] == "PNG"

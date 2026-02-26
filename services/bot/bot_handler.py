"""
PowerPoint Bot Handler
Handles conversation turns — accepts presentation requests and file uploads,
polls the orchestrator, and returns download links.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from microsoft.agents.builder import ActivityHandler, TurnContext, TurnState

logger = logging.getLogger(__name__)

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8080")
POLL_INTERVAL_SECONDS = 5
MAX_POLL_SECONDS = 300  # 5 minutes max


class PowerPointBotHandler(ActivityHandler):
    """
    Handles:
    - Message activities: user types a presentation request
    - File upload (attachment): user sends a PPTX file  
    - Conversation update: welcome message on join
    """

    def __init__(self, conv_state: Any, user_state: Any) -> None:
        super().__init__()
        self._conv_state = conv_state
        self._user_state = user_state

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        """Handle incoming messages and file attachments."""
        activity = turn_context.activity
        user_text = (activity.text or "").strip()
        user_id = activity.from_property.id if activity.from_property else "user"
        conversation_id = activity.conversation.id if activity.conversation else "default"

        # ── Check for PPTX file attachment ────────────────────────────────────
        uploaded_blob = ""
        if activity.attachments:
            for attachment in activity.attachments:
                if attachment.content_type in (
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/octet-stream",
                ):
                    # Download and re-upload to orchestrator's upload endpoint
                    try:
                        uploaded_blob = await self._upload_attachment(attachment)
                        await turn_context.send_activity(
                            f"✅ Received your presentation file. I'll use it as a starting point.\n"
                            f"Please also tell me what changes or new content you'd like."
                        )
                    except Exception as e:
                        logger.warning("Could not process attachment: %s", e)
                        await turn_context.send_activity(
                            "⚠️ I couldn't process that file. Please try again or describe what you need."
                        )

        if not user_text and not uploaded_blob:
            await turn_context.send_activity(
                "Please describe the presentation you'd like me to create. "
                "You can also upload an existing PPTX file as a starting point."
            )
            return

        if not user_text and uploaded_blob:
            user_text = "Analyze this presentation and create an improved version."

        # ── Send thinking indicator ───────────────────────────────────────────
        await turn_context.send_activity("🔍 Researching your topic and building the presentation...")

        # ── Submit job to orchestrator ────────────────────────────────────────
        try:
            job_id = await self._submit_job(
                user_id=user_id,
                conversation_id=conversation_id,
                message=user_text,
                uploaded_blob=uploaded_blob,
            )
        except Exception as e:
            logger.exception("Failed to submit job")
            await turn_context.send_activity(
                f"❌ Sorry, I couldn't start the generation. Please try again.\nError: {e}"
            )
            return

        await turn_context.send_activity(
            f"✅ Job started! I'll notify you when your presentation is ready. "
            f"(Job ID: `{job_id}`)"
        )

        # ── Poll for result ───────────────────────────────────────────────────
        result = await self._poll_job(job_id)

        if result.get("status") == "completed":
            download_url = result.get("download_url", "")
            slide_count = result.get("slide_count", 0)
            file_size_kb = result.get("file_size_kb", 0)
            await turn_context.send_activity(
                f"🎉 **Your presentation is ready!**\n\n"
                f"📊 Slides: {slide_count} | 📦 Size: {file_size_kb:.0f} KB\n\n"
                f"[⬇️ Download your presentation]({download_url})\n\n"
                f"_Link expires in 72 hours._"
            )
        else:
            error = result.get("error", "Unknown error")
            await turn_context.send_activity(
                f"❌ I'm sorry, something went wrong while creating your presentation.\n\n"
                f"Error: {error}\n\nPlease try again."
            )

    async def on_members_added_activity(
        self, members_added: list[Any], turn_context: TurnContext
    ) -> None:
        """Send welcome message when bot/user joins."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 **Welcome to PowerPoint Agent!**\n\n"
                    "I can create professional PowerPoint presentations for you. Just tell me:\n\n"
                    "• **What topic** you need a presentation on\n"
                    "• **Your audience** (optional)\n"
                    "• **Number of slides** (optional, default: 10)\n\n"
                    "You can also **upload an existing PPTX file** and I'll use it as a starting point.\n\n"
                    "_Example: 'Create a 12-slide pitch deck for a B2B SaaS product targeting CTOs'_"
                )

    async def _submit_job(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        uploaded_blob: str = "",
    ) -> str:
        """Submit a generation job to the orchestrator."""
        payload: dict[str, Any] = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "message": message,
            "uploaded_document_blob": uploaded_blob,
            "language": "en",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{ORCHESTRATOR_URL}/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["job_id"]

    async def _poll_job(self, job_id: str) -> dict[str, Any]:
        """Poll job status until completed, failed, or timeout."""
        elapsed = 0
        async with httpx.AsyncClient(timeout=15.0) as client:
            while elapsed < MAX_POLL_SECONDS:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                elapsed += POLL_INTERVAL_SECONDS
                try:
                    resp = await client.get(f"{ORCHESTRATOR_URL}/jobs/{job_id}")
                    resp.raise_for_status()
                    data = resp.json()
                    status = data.get("status", "")
                    if status in ("completed", "failed"):
                        return data
                except Exception as e:
                    logger.warning("Poll error for job %s: %s", job_id, e)

        return {"status": "failed", "error": "Timeout waiting for presentation generation"}

    async def _upload_attachment(self, attachment: Any) -> str:
        """Download attachment from Teams/DirectLine and re-upload to orchestrator."""
        content_url = getattr(attachment, "content_url", "") or ""
        if not content_url:
            raise ValueError("Attachment has no content_url")

        async with httpx.AsyncClient(timeout=60.0) as client:
            # May need auth token for Teams-hosted content
            resp = await client.get(content_url)
            resp.raise_for_status()
            file_bytes = resp.content

        filename = getattr(attachment, "name", "upload.pptx") or "upload.pptx"

        import io
        from aiohttp import FormData
        # Upload to orchestrator
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")}
            data = {"user_id": "bot"}
            resp = await client.post(f"{ORCHESTRATOR_URL}/upload", files=files, data=data)
            resp.raise_for_status()
            result = resp.json()

        return result.get("blob_name", "")

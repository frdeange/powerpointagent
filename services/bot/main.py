"""
Bot Service — M365 Agents SDK (microsoft-agents-hosting-aiohttp)
Handles Web Chat (DirectLine) and Microsoft Teams channels.
Web Chat is the primary channel; Teams is secondary.
"""

from __future__ import annotations

import logging
import os
import asyncio
from typing import Any

from aiohttp import web

from microsoft.agents.hosting.aiohttp import CloudAdapter, app_error_handler
from microsoft.agents.builder import (
    AgentApplication,
    TurnState,
    ConversationState,
    UserState,
)
from microsoft.agents.storage import MemoryStorage
from microsoft.agents.core.models import Activity, ActivityTypes

from bot_handler import PowerPointBotHandler

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


def create_adapter() -> CloudAdapter:
    """Create the Bot Framework cloud adapter."""
    from microsoft.agents.authentication import MsalConnectionManager

    return CloudAdapter(
        connection_manager=MsalConnectionManager(
            app_id=os.environ["MICROSOFT_APP_ID"],
            app_password=os.environ["MICROSOFT_APP_PASSWORD"],
            tenant_id=os.environ.get("MICROSOFT_APP_TENANT_ID", ""),
        )
    )


async def create_app() -> web.Application:
    adapter = create_adapter()
    storage = MemoryStorage()  # Replace with CosmosDB/Azure Tables for production
    conv_state = ConversationState(storage)
    user_state = UserState(storage)

    bot_handler = PowerPointBotHandler(conv_state, user_state)

    # ── aiohttp web app ───────────────────────────────────────────────────────
    web_app = web.Application(middlewares=[app_error_handler])

    # Bot Framework messages endpoint
    async def messages(request: web.Request) -> web.Response:
        return await adapter.process(request, bot_handler)

    # Health check
    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "bot"})

    web_app.router.add_post("/api/messages", messages)
    web_app.router.add_get("/health", health)
    web_app.router.add_get("/", lambda r: web.HTTPFound("/web/index.html"))

    # Serve the Web Chat UI as static files
    web_chat_dir = os.path.join(os.path.dirname(__file__), "web", "static")
    web_app.router.add_static("/web", web_chat_dir, show_index=True)

    return web_app


def main() -> None:
    port = int(os.environ.get("PORT", "3978"))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = loop.run_until_complete(create_app())
    web.run_app(app, host="0.0.0.0", port=port)
    logger.info("Bot service running on port %d", port)


if __name__ == "__main__":
    main()

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.routes import chat, courses, health, root
from app.config import get_settings
from app.mcp_server.server import create_mcp_transport, transport_security_for_url

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

class _MCPAppProxy:
    """Stable mount point whose transport is replaced for each app lifespan."""

    app: ASGIApp | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.app is None:
            response = JSONResponse({"error": "MCP server is not running"}, status_code=503)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


mcp_proxy = _MCPAppProxy() if settings.mcp_token else None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if mcp_proxy is None:
        yield
        return

    transport, session_manager = create_mcp_transport(
        mcp_token=settings.mcp_token,
        transport_security=transport_security_for_url(settings.mcp_server_url),
    )
    mcp_proxy.app = transport
    try:
        async with session_manager.run():
            yield
    finally:
        mcp_proxy.app = None

app = FastAPI(
    title="DTU Course API",
    description="Chat-based course recommendations and a searchable official DTU course catalogue.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")

app.include_router(root.router)
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(courses.router)

if mcp_proxy is not None:
    app.mount("/mcp", mcp_proxy)

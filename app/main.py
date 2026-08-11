import logging

from fastapi import FastAPI

from app.api.routes import courses, health
from app.config import get_settings

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = FastAPI(
    title="DTU Course API",
    description="Searchable official DTU course catalogue for Copilot Studio.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
app.include_router(health.router)
app.include_router(courses.router)


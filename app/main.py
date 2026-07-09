"""
Application entry point. Run with:

    uvicorn app.main:app --reload

This file's only job is wiring things together: create the app, set up
logging, register routers. All actual logic lives in the routers/services
it imports.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api import chat, documents, health, search, upload
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("%s starting up (env=%s)", settings.app_name, settings.environment)
    yield
    logger.info("%s shutting down", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description=(
        "Enterprise AI Knowledge & Engineering Assistant -- upload internal "
        "documents (manuals, specs, reports) and ask questions over them "
        "with citations, plus get executive summaries and requirement "
        "extraction."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


app.include_router(health.router)
app.include_router(auth_router)
app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(search.router)
app.include_router(documents.router)

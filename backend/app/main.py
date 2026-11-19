"""FastAPI application factory and startup/shutdown lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, health, sessions, voice
from app.config import settings
from app.database import engine, init_db
from app.services.llm_service import llm_service
from app.services.stt_service import stt_service
from app.services.tts_service import tts_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and AI services on startup."""
    logger.info("Starting %s v%s...", settings.app_name, settings.app_version)
    await init_db()
    await stt_service.load_model()
    await tts_service.load_model()
    await llm_service.initialize()
    yield
    await engine.dispose()
    logger.info("Shutting down %s...", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from fastapi.staticfiles import StaticFiles

app.include_router(health.router)
app.include_router(voice.router)
app.include_router(chat.router)
app.include_router(sessions.router)

# Mount built React frontend when available (e.g. unified Render cloud deployment)
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/dist"))
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")

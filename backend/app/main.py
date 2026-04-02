from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.db.database import Base, engine

app = FastAPI(
    title="inVision U Screening API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS must be added BEFORE routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://invision-u-seven.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}


# Import routes AFTER middleware
from app.api.routes import router
app.include_router(router, prefix="/api")

# Serve generated TTS audio files AFTER routes
audio_dir = Path(settings.AUDIO_CACHE_DIR)
audio_dir.mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

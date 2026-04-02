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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://invision-u-seven.vercel.app"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve generated TTS audio files
audio_dir = Path(settings.AUDIO_CACHE_DIR)
audio_dir.mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}


from app.api.routes import router
app.include_router(router, prefix="/api")

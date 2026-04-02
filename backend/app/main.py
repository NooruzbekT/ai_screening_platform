from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a JSON 500 with CORS headers so the browser can read the error.

    Starlette's CORSMiddleware only processes responses that pass through the
    normal middleware stack; unhandled exceptions bypass it and arrive at the
    client without CORS headers, causing a confusing network error instead of
    the real error message.  This handler re-attaches the appropriate
    Access-Control-Allow-Origin header before the response leaves the server.

    OPTIONS preflight requests are excluded: the exception handler must not
    intercept them because doing so returns a 500 before CORSMiddleware can
    attach the required Access-Control-* headers, causing the browser to block
    the subsequent real request.
    """
    if request.method == "OPTIONS":
        # Let CORSMiddleware handle the preflight response entirely.
        from starlette.responses import Response
        return Response(status_code=200)

    origin = request.headers.get("origin", "")
    headers = {}
    if origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
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

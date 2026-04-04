from fastapi import FastAPI, HTTPException, Request
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

# CORS must be added BEFORE routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a JSON response with CORS headers so the browser can read the error.

    Starlette's CORSMiddleware only processes responses that pass through the
    normal middleware stack; unhandled exceptions bypass it and arrive at the
    client without CORS headers, causing a confusing network error instead of
    the real error message.  This handler re-attaches the appropriate
    Access-Control-Allow-Origin header before the response leaves the server.

    HTTPExceptions (e.g. the 400 raised by password-length validation) are
    returned with their original status code and detail so the frontend can
    display the correct error rather than a generic 500.
    """
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_jury_account()
    from download_models import download_models
    download_models()
    from app.models.nlp_model import nlp_model
    nlp_model._ensure_ready()


def _ensure_jury_account() -> None:
    from passlib.context import CryptContext
    from app.db.database import SessionLocal
    from app.db.models import User, UserRole

    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.JURY_EMAIL).first():
            db.add(User(
                email=settings.JURY_EMAIL,
                password_hash=pwd.hash(settings.JURY_PASSWORD),
                full_name="Приёмная комиссия",
                role=UserRole.reviewer,
            ))
            db.commit()
    finally:
        db.close()


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

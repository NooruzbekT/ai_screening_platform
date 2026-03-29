from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    DATABASE_URL: str = "postgresql://user:pass@db:5432/invisionu"

    JWT_SECRET: str = "change-me-use-min-32-chars-random-string-here"
    JWT_EXPIRE_HOURS: int = 24

    NLP_MODEL_EN: str = "models_trained/roberta_en.pkl"
    NLP_MODEL_RU: str = "models_trained/rubert_ru.pkl"
    NLP_MODEL_KZ: str = "models_trained/mbert_kz.pkl"
    NLP_FALLBACK_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"

    WHISPER_MODEL: str = "medium"

    TTS_VOICE_RU: str = "ru-RU-SvetlanaNeural"
    TTS_VOICE_KZ: str = "kk-KZ-AigulNeural"
    TTS_VOICE_EN: str = "en-US-JennyNeural"
    AUDIO_CACHE_DIR: str = "audio_cache"

    ZONE_A_THRESHOLD: float = 8.0
    ZONE_B_THRESHOLD: float = 6.0
    AI_DETECTOR_THRESHOLD: float = 0.60
    CONSISTENCY_THRESHOLD: float = 0.60
    NLP_WEIGHT: float = 0.70
    STRUCT_WEIGHT: float = 0.30

    BASE_DIR: Path = Path(__file__).parent.parent.parent

    model_config = {
        "env_file": str(Path(__file__).parent.parent.parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()

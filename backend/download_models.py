"""Download trained .pkl models from HuggingFace Hub at container startup."""

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

MODELS = ["roberta_en.pkl", "rubert_ru.pkl", "mbert_kz.pkl"]
MODELS_DIR = Path(__file__).parent / "models_trained"


def download_models() -> None:
    hf_token = os.getenv("HF_TOKEN")
    hf_repo = os.getenv("HF_REPO_ID")  # например: yourname/invisionu-models

    if not hf_token or not hf_repo:
        log.warning("HF_TOKEN or HF_REPO_ID not set — skipping model download, fallback MiniLM will be used")
        return

    try:
        from huggingface_hub import hf_hub_download

        MODELS_DIR.mkdir(exist_ok=True)

        for filename in MODELS:
            dest = MODELS_DIR / filename
            if dest.exists():
                log.info("Model %s already exists, skipping", filename)
                continue
            log.info("Downloading %s from HuggingFace Hub...", filename)
            hf_hub_download(
                repo_id=hf_repo,
                filename=filename,
                repo_type="model",
                token=hf_token,
                local_dir=str(MODELS_DIR),
            )
            log.info("Downloaded %s (%.1f MB)", filename, dest.stat().st_size / 1024 / 1024)

    except Exception as exc:
        log.error("Model download failed: %s — fallback MiniLM will be used", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    download_models()

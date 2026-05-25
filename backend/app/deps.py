"""Settings + KB singleton."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from .kb import KnowledgeBase

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    kb_persist_dir: Path
    kb_upload_dir: Path
    kb_collection: str
    cors_origins: list[str]
    log_level: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Create a key at "
            "https://aistudio.google.com/app/apikey and set it in .env"
        )
    base = Path(__file__).resolve().parent.parent  # backend/
    return Settings(
        gemini_api_key=api_key,
        kb_persist_dir=Path(os.getenv("KB_PERSIST_DIR", str(base / "chroma_db"))),
        kb_upload_dir=Path(os.getenv("KB_UPLOAD_DIR", str(base / "uploads"))),
        kb_collection=os.getenv("KB_COLLECTION", "multimodal_kb"),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    s = get_settings()
    logger.info(
        "Initialising KnowledgeBase (persist=%s, upload=%s, collection=%s)",
        s.kb_persist_dir, s.kb_upload_dir, s.kb_collection,
    )
    return KnowledgeBase(
        api_key=s.gemini_api_key,
        collection_name=s.kb_collection,
        persist_dir=s.kb_persist_dir,
        upload_dir=s.kb_upload_dir,
    )

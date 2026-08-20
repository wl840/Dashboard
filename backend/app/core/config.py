from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


def _project_path(environment_name: str, default: str) -> Path:
    configured = Path(os.getenv(environment_name, default))
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / configured


@dataclass(frozen=True)
class Settings:
    app_name: str
    database_path: Path
    source_data_dir: Path
    frontend_origin: str
    ai_provider: str
    ai_api_key: str | None
    ai_base_url: str | None
    ai_model: str | None


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name="Moneki Operations API",
        database_path=_project_path("DATABASE_PATH", "backend/data/dashboard.db"),
        source_data_dir=_project_path("SOURCE_DATA_DIR", "data"),
        frontend_origin=os.getenv("FRONTEND_ORIGIN", "http://localhost:5173"),
        ai_provider=os.getenv("AI_PROVIDER", "mock").strip().lower(),
        ai_api_key=os.getenv("AI_API_KEY") or None,
        ai_base_url=os.getenv("AI_BASE_URL") or None,
        ai_model=os.getenv("AI_MODEL") or None,
    )


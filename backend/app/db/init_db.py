from app.core.config import get_settings
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.services.ingestion import ImportSummary, ensure_data_loaded


def initialize_database() -> ImportSummary:
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        return ensure_data_loaded(session, get_settings().source_data_dir)

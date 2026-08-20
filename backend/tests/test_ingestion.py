from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import DataQualityIssue, RawSale, Sale
from app.db.session import create_sqlite_engine
from app.services.ingestion import ensure_data_loaded

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATA_DIR = PROJECT_ROOT / "data"


def _test_session(tmp_path: Path) -> Session:
    engine = create_sqlite_engine(tmp_path / "test-dashboard.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory()


def test_import_builds_auditable_canonical_dataset(tmp_path: Path) -> None:
    with _test_session(tmp_path) as session:
        summary = ensure_data_loaded(session, SOURCE_DATA_DIR)

        assert summary.raw_rows == 12_131
        assert summary.canonical_orders == 12_051
        assert summary.valid_orders == 11_858
        assert session.scalar(select(func.count()).select_from(RawSale)) == 12_131
        assert session.scalar(select(func.count()).select_from(Sale)) == 12_051
        assert session.scalar(
            select(func.sum(Sale.amount_cents)).where(Sale.is_valid.is_(True))
        ) == 42_660_100

        issue_codes = set(session.scalars(select(DataQualityIssue.code)))
        assert {
            "duplicate_exact",
            "duplicate_conflict",
            "missing_amount",
            "unknown_store",
            "unknown_product",
        }.issubset(issue_codes)


def test_import_is_idempotent_for_unchanged_source(tmp_path: Path) -> None:
    with _test_session(tmp_path) as session:
        first = ensure_data_loaded(session, SOURCE_DATA_DIR)
        second = ensure_data_loaded(session, SOURCE_DATA_DIR)

        assert first.dataset_hash == second.dataset_hash
        assert second.reused is True
        assert session.scalar(select(func.count()).select_from(Sale)) == 12_051

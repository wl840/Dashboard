from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import create_sqlite_engine
from app.repositories.analytics import AnalyticsRepository
from app.services.ingestion import ensure_data_loaded

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _repository(tmp_path: Path) -> tuple[Session, AnalyticsRepository]:
    engine = create_sqlite_engine(tmp_path / "analytics.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    ensure_data_loaded(session, PROJECT_ROOT / "data")
    return session, AnalyticsRepository(session)


def test_dashboard_metrics_reconcile_to_daily_rows(tmp_path: Path) -> None:
    session, repository = _repository(tmp_path)
    with session:
        result = repository.dashboard()

        assert result["range"] == {
            "start_date": date(2026, 5, 1),
            "end_date": date(2026, 7, 31),
        }
        assert result["summary"]["revenue_cents"] == 42_660_100
        assert result["summary"]["order_count"] == 11_858
        assert result["summary"]["aov_cents"] == 3_598
        assert sum(row["revenue_cents"] for row in result["daily"]) == 42_660_100
        assert sum(row["order_count"] for row in result["daily"]) == 11_858
        assert len(result["top_products"]) == 10
        assert result["top_products"] == sorted(
            result["top_products"],
            key=lambda row: (-row["revenue_cents"], row["product_id"]),
        )


def test_business_questions_use_the_same_repository(tmp_path: Path) -> None:
    session, repository = _repository(tmp_path)
    with session:
        categories = repository.rank_store_categories()
        beef_poke = repository.product_revenue(
            "牛肉poke", date(2026, 6, 1), date(2026, 6, 30)
        )
        aov = repository.compare_recent_monthly_aov()

        assert categories["rows"][0]["category"] == "日料"
        assert beef_poke["revenue_cents"] == 1_352_400
        assert beef_poke["order_count"] == 182
        assert aov["previous"]["aov_cents"] == 3_523
        assert aov["current"]["aov_cents"] == 3_605
        assert aov["direction"] == "up"
        assert aov["change_pct"] == 2.3

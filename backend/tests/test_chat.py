from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.session import create_sqlite_engine
from app.schemas.chat import ChatRequest
from app.services.chat import GroundedChatService
from app.services.ingestion import ensure_data_loaded

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _service(tmp_path: Path) -> tuple[Session, GroundedChatService]:
    engine = create_sqlite_engine(tmp_path / "chat.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    ensure_data_loaded(session, PROJECT_ROOT / "data")
    return session, GroundedChatService(session)


def test_required_questions_are_grounded_in_database_results(tmp_path: Path) -> None:
    session, service = _service(tmp_path)
    with session:
        category = service.answer(ChatRequest(message="哪个品类的门店营业额最高？"))
        product = service.answer(ChatRequest(message="牛肉poke 六月卖了多少钱？"))
        aov = service.answer(ChatRequest(message="客单价最近是涨了还是跌了？"))

        assert category["evidence"]["result"]["rows"][0]["category"] == "日料"
        assert "日料" in category["answer"]
        assert product["evidence"]["result"]["revenue_cents"] == 1_352_400
        assert "¥13,524.00" in product["answer"]
        assert aov["evidence"]["result"]["current"]["aov_cents"] == 3_605
        assert aov["evidence"]["result"]["previous"]["aov_cents"] == 3_523
        assert "上涨" in aov["answer"]


def test_follow_up_reuses_product_context_and_unknown_questions_do_not_guess(
    tmp_path: Path,
) -> None:
    session, service = _service(tmp_path)
    with session:
        june = service.answer(ChatRequest(message="牛肉poke 六月卖了多少钱？"))
        may = service.answer(
            ChatRequest(message="那五月呢？", context=june["context"])
        )
        unsupported = service.answer(ChatRequest(message="明天天气怎么样？"))

        assert may["evidence"]["result"]["product_name"] == "牛肉poke"
        assert str(may["evidence"]["result"]["period"]["start_date"]) == "2026-05-01"
        assert unsupported["evidence"] is None
        assert "不会猜测" in unsupported["answer"]

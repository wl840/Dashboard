from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.planner import AnalyticsPlanner
from app.ai.tools import chart_action, execute_tool, render_grounded_answer
from app.core.config import Settings, get_settings
from app.repositories.analytics import AnalyticsRepository
from app.schemas.chat import ChatRequest


class GroundedChatService:
    def __init__(self, session: Session, settings: Settings | None = None):
        self.repository = AnalyticsRepository(session)
        self.settings = settings or get_settings()
        self.planner = AnalyticsPlanner(self.settings)

    def answer(self, request: ChatRequest) -> dict[str, Any]:
        metadata = self.repository.metadata()
        product_names = [item["product_name"] for item in metadata["products"]]
        dataset_end = metadata["date_range"]["end_date"]
        planning = self.planner.plan(
            request.message,
            request.context,
            product_names,
            dataset_end,
        )
        if planning.plan is None:
            return {
                "answer": (
                    "这份数据目前支持营业额、订单数、客单价、门店品类排名和"
                    "商品销售查询。你的问题无法从现有字段可靠回答，我不会猜测。"
                ),
                "provider": planning.provider,
                "tool_name": None,
                "context": request.context,
                "evidence": None,
                "chart_action": None,
                "fallback_reason": planning.fallback_reason,
            }

        result = execute_tool(self.repository, planning.plan)
        context = {
            "tool_name": planning.plan.name,
            "arguments": dict(planning.plan.arguments),
        }
        if result.get("status") == "ok" and result.get("product_name"):
            context["arguments"]["product_name"] = result["product_name"]
        quality = self.repository.quality_snapshot(compact=True)
        return {
            "answer": render_grounded_answer(planning.plan, result),
            "provider": planning.provider,
            "tool_name": planning.plan.name,
            "context": context,
            "evidence": {
                "source": "SQLite canonical sales",
                "tool": planning.plan.name,
                "parameters": planning.plan.arguments,
                "result": result,
                "metric_policy": (
                    "仅统计日期可解析、金额大于零且数量大于零的去重订单；"
                    "金额以整数分汇总。"
                ),
                "coverage": {
                    "valid_orders": quality["valid_orders"],
                    "canonical_orders": quality["canonical_orders"],
                    "coverage_pct": quality["coverage_pct"],
                },
            },
            "chart_action": chart_action(planning.plan, result),
            "fallback_reason": planning.fallback_reason,
        }

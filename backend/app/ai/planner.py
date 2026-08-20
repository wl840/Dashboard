from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import date
from typing import Any

import httpx

from app.ai.tools import ALLOWED_TOOL_NAMES, OPENAI_TOOLS
from app.ai.types import PlannedTool, PlanningResult
from app.core.config import Settings

MONTH_NAMES = {
    "一月": 1,
    "二月": 2,
    "三月": 3,
    "四月": 4,
    "五月": 5,
    "六月": 6,
    "七月": 7,
    "八月": 8,
    "九月": 9,
    "十月": 10,
    "十一月": 11,
    "十二月": 12,
}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _month_range(message: str, default_year: int) -> tuple[date, date] | None:
    year_match = re.search(r"(20\d{2})\s*年?", message)
    year = int(year_match.group(1)) if year_match else default_year
    month: int | None = None
    for label, number in MONTH_NAMES.items():
        if label in message:
            month = number
            break
    if month is None:
        month_match = re.search(r"(?<!\d)(1[0-2]|0?[1-9])\s*月", message)
        if month_match:
            month = int(month_match.group(1))
    if month is None:
        return None
    start = date(year, month, 1)
    return start, date(year, month, monthrange(year, month)[1])


def _local_plan(
    message: str,
    context: dict[str, Any],
    product_names: list[str],
    dataset_end: date,
) -> PlannedTool | None:
    compact = _normalized(message)
    month = _month_range(message, dataset_end.year)
    previous_tool = context.get("tool_name")
    previous_arguments = dict(context.get("arguments") or {})

    matched_product = next(
        (name for name in product_names if _normalized(name) in compact), None
    )
    if (
        matched_product is None
        and month
        and previous_tool == "get_product_revenue"
        and previous_arguments.get("product_name")
    ):
        matched_product = str(previous_arguments["product_name"])

    if matched_product:
        arguments: dict[str, Any] = {"product_name": matched_product}
        if month:
            arguments.update(
                start_date=month[0].isoformat(), end_date=month[1].isoformat()
            )
        return PlannedTool("get_product_revenue", arguments)

    if "品类" in compact and any(
        word in compact for word in ("最高", "最多", "第一", "排名")
    ):
        arguments = {}
        if month:
            arguments.update(
                start_date=month[0].isoformat(), end_date=month[1].isoformat()
            )
        return PlannedTool("rank_store_categories", arguments)

    if "客单价" in compact and any(
        word in compact for word in ("最近", "趋势", "上涨", "下跌", "涨", "跌")
    ):
        return PlannedTool("compare_recent_monthly_aov", {})

    if any(word in compact for word in ("营业额", "订单数", "客单价", "经营情况")):
        arguments = {}
        if month:
            arguments.update(
                start_date=month[0].isoformat(), end_date=month[1].isoformat()
            )
        return PlannedTool("get_period_summary", arguments)
    return None


class AnalyticsPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def plan(
        self,
        message: str,
        context: dict[str, Any],
        product_names: list[str],
        dataset_end: date,
    ) -> PlanningResult:
        if (
            self.settings.ai_provider == "mock"
            or not self.settings.ai_api_key
            or not self.settings.ai_base_url
            or not self.settings.ai_model
        ):
            return PlanningResult(
                _local_plan(message, context, product_names, dataset_end), "mock"
            )

        try:
            endpoint = (
                f"{self.settings.ai_base_url.rstrip('/')}/chat/completions"
            )
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.settings.ai_api_key}"},
                json={
                    "model": self.settings.ai_model,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是餐饮数据分析意图解析器。必须选择一个提供的工具，"
                                "不能自行计算或编造数字。日期数据截止到 "
                                f"{dataset_end.isoformat()}。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "question": message,
                                    "previous_context": context,
                                    "known_products": product_names,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "tools": OPENAI_TOOLS,
                    "tool_choice": "auto",
                },
                timeout=30,
            )
            response.raise_for_status()
            message_payload = response.json()["choices"][0]["message"]
            tool_calls = message_payload.get("tool_calls") or []
            if not tool_calls:
                raise ValueError("Model did not select an analytics tool")
            function = tool_calls[0]["function"]
            if function["name"] not in ALLOWED_TOOL_NAMES:
                raise ValueError("Model selected a tool outside the allowlist")
            arguments = json.loads(function.get("arguments") or "{}")
            return PlanningResult(
                PlannedTool(function["name"], arguments),
                self.settings.ai_provider,
            )
        except Exception as exc:
            return PlanningResult(
                _local_plan(message, context, product_names, dataset_end),
                "mock_fallback",
                fallback_reason=type(exc).__name__,
            )

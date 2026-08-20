from __future__ import annotations

from datetime import date
from typing import Any

from app.ai.types import PlannedTool
from app.repositories.analytics import AnalyticsRepository

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rank_store_categories",
            "description": "按营业额对门店品类进行排序。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_revenue",
            "description": "查询一个商品在指定日期区间的营业额、订单数和销量。",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                },
                "required": ["product_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_recent_monthly_aov",
            "description": "比较数据中最近两个月的客单价，判断上涨或下跌。",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_period_summary",
            "description": "查询指定日期区间的营业额、订单数和客单价。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                    "store_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
]

ALLOWED_TOOL_NAMES = {
    tool["function"]["name"] for tool in OPENAI_TOOLS
}


def _optional_date(arguments: dict[str, Any], key: str) -> date | None:
    value = arguments.get(key)
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def execute_tool(
    repository: AnalyticsRepository, plan: PlannedTool
) -> dict[str, Any]:
    if plan.name not in ALLOWED_TOOL_NAMES:
        raise ValueError(f"Unsupported analytics tool: {plan.name}")
    start_date = _optional_date(plan.arguments, "start_date")
    end_date = _optional_date(plan.arguments, "end_date")

    if plan.name == "rank_store_categories":
        return repository.rank_store_categories(start_date, end_date)
    if plan.name == "get_product_revenue":
        product_name = str(plan.arguments.get("product_name", "")).strip()
        if not product_name:
            raise ValueError("product_name is required")
        return repository.product_revenue(product_name, start_date, end_date)
    if plan.name == "compare_recent_monthly_aov":
        return repository.compare_recent_monthly_aov()
    return repository.period_summary(
        start_date=start_date,
        end_date=end_date,
        store_id=plan.arguments.get("store_id"),
    )


def render_grounded_answer(plan: PlannedTool, result: dict[str, Any]) -> str:
    if plan.name == "rank_store_categories":
        rows = result["rows"]
        if not rows:
            return "这个时间范围内没有可用的门店品类销售数据。"
        top = rows[0]
        period = result["period"]
        return (
            f"{period['start_date']:%Y-%m-%d} 至 {period['end_date']:%Y-%m-%d}，"
            f"营业额最高的门店品类是「{top['category']}」，"
            f"营业额为 ¥{top['revenue']}，共 {top['order_count']:,} 笔有效订单。"
        )

    if plan.name == "get_product_revenue":
        status = result["status"]
        if status == "not_found":
            return (
                f"商品维表中找不到「{result['product_name']}」，"
                "我不会用相似商品的数据代替。你可以换一个商品名再问。"
            )
        if status == "ambiguous":
            candidates = "、".join(result["candidates"])
            return f"商品名称存在歧义，请从以下商品中选择：{candidates}。"
        period = result["period"]
        return (
            f"{period['start_date']:%Y-%m-%d} 至 {period['end_date']:%Y-%m-%d}，"
            f"「{result['product_name']}」营业额为 ¥{result['revenue']}，"
            f"售出 {result['qty']:,} 份，涉及 {result['order_count']:,} 笔有效订单。"
        )

    if plan.name == "compare_recent_monthly_aov":
        current = result["current"]
        previous = result["previous"]
        direction_text = {"up": "上涨", "down": "下跌", "flat": "持平"}[
            result["direction"]
        ]
        change = result["change_pct"]
        change_text = f"{abs(change):.1f}%" if change is not None else "无法计算"
        return (
            f"最近一个月客单价为 ¥{current['aov']}，"
            f"上一个月为 ¥{previous['aov']}，因此客单价{direction_text}了 {change_text}。"
        )

    period = result["period"]
    summary = result["summary"]
    return (
        f"{period['start_date']:%Y-%m-%d} 至 {period['end_date']:%Y-%m-%d}，"
        f"营业额为 ¥{summary['revenue']}，"
        f"有效订单 {summary['order_count']:,} 笔，客单价 ¥{summary['aov']}。"
    )


def chart_action(plan: PlannedTool, result: dict[str, Any]) -> dict[str, Any] | None:
    if plan.name == "compare_recent_monthly_aov":
        return {
            "type": "apply_date_range",
            "start_date": result["previous"]["start_date"],
            "end_date": result["current"]["end_date"],
        }
    period = result.get("period")
    if not period:
        return None
    action: dict[str, Any] = {
        "type": "apply_date_range",
        "start_date": period["start_date"],
        "end_date": period["end_date"],
    }
    if result.get("product_id"):
        action["highlight_product_id"] = result["product_id"]
    return action

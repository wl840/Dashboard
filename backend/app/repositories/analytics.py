from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.models import DataQualityIssue, ImportRun, Product, Sale, Store


def _rounded_ratio(numerator: int, denominator: int) -> int:
    if not denominator:
        return 0
    return int(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _percentage_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return None
    result = ((Decimal(current) - Decimal(previous)) / Decimal(previous) * 100).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    return float(result)


def _money(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


class AnalyticsRepository:
    """The single source of truth for dashboard APIs and AI tools."""

    def __init__(self, session: Session):
        self.session = session

    def dataset_range(self) -> tuple[date, date]:
        result = self.session.execute(
            select(func.min(Sale.sale_date), func.max(Sale.sale_date)).where(
                Sale.is_valid.is_(True)
            )
        ).one()
        if result[0] is None or result[1] is None:
            raise RuntimeError("No valid sales data is available")
        return result[0], result[1]

    def _resolved_range(
        self, start_date: date | None, end_date: date | None
    ) -> tuple[date, date]:
        dataset_start, dataset_end = self.dataset_range()
        resolved_start = start_date or dataset_start
        resolved_end = end_date or dataset_end
        if resolved_start > resolved_end:
            raise ValueError("start_date must be on or before end_date")
        return resolved_start, resolved_end

    @staticmethod
    def _filters(start_date: date, end_date: date, store_id: str | None = None):
        filters = [
            Sale.is_valid.is_(True),
            Sale.sale_date >= start_date,
            Sale.sale_date <= end_date,
        ]
        if store_id:
            filters.append(Sale.store_id == store_id.strip().upper())
        return filters

    def _summary(
        self, start_date: date, end_date: date, store_id: str | None = None
    ) -> dict[str, Any]:
        revenue, orders = self.session.execute(
            select(
                func.coalesce(func.sum(Sale.amount_cents), 0),
                func.count(distinct(Sale.order_id)),
            ).where(*self._filters(start_date, end_date, store_id))
        ).one()
        revenue_cents = int(revenue or 0)
        order_count = int(orders or 0)
        aov_cents = _rounded_ratio(revenue_cents, order_count)
        return {
            "revenue_cents": revenue_cents,
            "revenue": _money(revenue_cents),
            "order_count": order_count,
            "aov_cents": aov_cents,
            "aov": _money(aov_cents),
        }

    def dashboard(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        store_id: str | None = None,
        top_limit: int = 10,
    ) -> dict[str, Any]:
        start_date, end_date = self._resolved_range(start_date, end_date)
        summary = self._summary(start_date, end_date, store_id)

        period_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        previous = self._summary(previous_start, previous_end, store_id)
        summary["revenue_change_pct"] = _percentage_change(
            summary["revenue_cents"], previous["revenue_cents"]
        )
        summary["orders_change_pct"] = _percentage_change(
            summary["order_count"], previous["order_count"]
        )
        summary["aov_change_pct"] = _percentage_change(
            summary["aov_cents"], previous["aov_cents"]
        )

        daily_revenue = func.sum(Sale.amount_cents).label("revenue_cents")
        daily_orders = func.count(distinct(Sale.order_id)).label("order_count")
        daily_rows = self.session.execute(
            select(Sale.sale_date, daily_revenue, daily_orders)
            .where(*self._filters(start_date, end_date, store_id))
            .group_by(Sale.sale_date)
            .order_by(Sale.sale_date)
        ).all()
        daily_by_date = {
            row.sale_date: {
                "revenue_cents": int(row.revenue_cents),
                "order_count": int(row.order_count),
            }
            for row in daily_rows
        }
        daily: list[dict[str, Any]] = []
        cursor = start_date
        while cursor <= end_date:
            values = daily_by_date.get(cursor, {"revenue_cents": 0, "order_count": 0})
            aov_cents = _rounded_ratio(
                values["revenue_cents"], values["order_count"]
            )
            daily.append(
                {
                    "date": cursor,
                    **values,
                    "aov_cents": aov_cents,
                }
            )
            cursor += timedelta(days=1)

        product_revenue = func.sum(Sale.amount_cents).label("revenue_cents")
        product_orders = func.count(distinct(Sale.order_id)).label("order_count")
        product_qty = func.sum(Sale.qty).label("qty")
        product_rows = self.session.execute(
            select(
                Sale.product_id,
                Product.product_name,
                Product.product_category,
                product_revenue,
                product_orders,
                product_qty,
            )
            .outerjoin(Product, Sale.product_id == Product.product_id)
            .where(*self._filters(start_date, end_date, store_id))
            .group_by(Sale.product_id, Product.product_name, Product.product_category)
            .order_by(product_revenue.desc(), Sale.product_id)
            .limit(top_limit)
        ).all()
        top_products = [
            {
                "rank": index,
                "product_id": row.product_id or "UNKNOWN",
                "product_name": row.product_name or f"未知商品（{row.product_id}）",
                "product_category": row.product_category or "未知",
                "revenue_cents": int(row.revenue_cents),
                "revenue": _money(int(row.revenue_cents)),
                "order_count": int(row.order_count),
                "qty": int(row.qty or 0),
            }
            for index, row in enumerate(product_rows, start=1)
        ]

        store_revenue = func.sum(Sale.amount_cents).label("revenue_cents")
        store_orders = func.count(distinct(Sale.order_id)).label("order_count")
        store_rows = self.session.execute(
            select(
                Sale.store_id,
                Store.store_name,
                Store.category,
                store_revenue,
                store_orders,
            )
            .outerjoin(Store, Sale.store_id == Store.store_id)
            .where(*self._filters(start_date, end_date, store_id))
            .group_by(Sale.store_id, Store.store_name, Store.category)
            .order_by(store_revenue.desc())
        ).all()
        store_performance = [
            {
                "store_id": row.store_id or "UNKNOWN",
                "store_name": row.store_name or "未知门店",
                "category": row.category or "未知",
                "revenue_cents": int(row.revenue_cents),
                "revenue": _money(int(row.revenue_cents)),
                "order_count": int(row.order_count),
                "aov_cents": _rounded_ratio(
                    int(row.revenue_cents), int(row.order_count)
                ),
            }
            for row in store_rows
        ]

        return {
            "range": {"start_date": start_date, "end_date": end_date},
            "filters": {"store_id": store_id},
            "summary": summary,
            "daily": daily,
            "top_products": top_products,
            "store_performance": store_performance,
            "quality": self.quality_snapshot(compact=True),
        }

    def metadata(self) -> dict[str, Any]:
        start_date, end_date = self.dataset_range()
        stores = self.session.scalars(select(Store).order_by(Store.store_id)).all()
        products = self.session.scalars(
            select(Product).order_by(Product.product_id)
        ).all()
        return {
            "date_range": {"start_date": start_date, "end_date": end_date},
            "stores": [
                {
                    "store_id": store.store_id,
                    "store_name": store.store_name,
                    "category": store.category,
                    "district": store.district,
                }
                for store in stores
            ],
            "products": [
                {
                    "product_id": product.product_id,
                    "product_name": product.product_name,
                    "product_category": product.product_category,
                }
                for product in products
            ],
        }

    def period_summary(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        store_id: str | None = None,
    ) -> dict[str, Any]:
        start_date, end_date = self._resolved_range(start_date, end_date)
        return {
            "period": {"start_date": start_date, "end_date": end_date},
            "store_id": store_id,
            "summary": self._summary(start_date, end_date, store_id),
        }

    def quality_snapshot(self, compact: bool = False) -> dict[str, Any]:
        latest_run = self.session.scalar(
            select(ImportRun).order_by(ImportRun.id.desc()).limit(1)
        )
        if latest_run is None:
            raise RuntimeError("Data has not been imported")
        coverage_pct = float(
            (
                Decimal(latest_run.valid_orders)
                / Decimal(latest_run.canonical_orders)
                * 100
            ).quantize(Decimal("0.1"))
        )
        result: dict[str, Any] = {
            "raw_rows": latest_run.raw_rows,
            "canonical_orders": latest_run.canonical_orders,
            "valid_orders": latest_run.valid_orders,
            "excluded_orders": latest_run.canonical_orders - latest_run.valid_orders,
            "coverage_pct": coverage_pct,
            "issue_count": latest_run.issue_count,
            "dataset_hash": latest_run.dataset_hash[:12],
            "imported_at": latest_run.imported_at,
        }
        if compact:
            return result

        code_rows = self.session.execute(
            select(DataQualityIssue.code, func.count(DataQualityIssue.id).label("count"))
            .group_by(DataQualityIssue.code)
            .order_by(func.count(DataQualityIssue.id).desc())
        ).all()
        severity_rows = self.session.execute(
            select(
                DataQualityIssue.severity,
                func.count(DataQualityIssue.id).label("count"),
            )
            .group_by(DataQualityIssue.severity)
            .order_by(func.count(DataQualityIssue.id).desc())
        ).all()
        result["issues_by_code"] = [
            {"code": row.code, "count": int(row.count)} for row in code_rows
        ]
        result["issues_by_severity"] = {
            row.severity: int(row.count) for row in severity_rows
        }
        return result

    def rank_store_categories(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> dict[str, Any]:
        start_date, end_date = self._resolved_range(start_date, end_date)
        revenue = func.sum(Sale.amount_cents).label("revenue_cents")
        orders = func.count(distinct(Sale.order_id)).label("order_count")
        rows = self.session.execute(
            select(Store.category, revenue, orders)
            .outerjoin(Store, Sale.store_id == Store.store_id)
            .where(*self._filters(start_date, end_date))
            .group_by(Store.category)
            .order_by(revenue.desc())
        ).all()
        return {
            "period": {"start_date": start_date, "end_date": end_date},
            "rows": [
                {
                    "category": row.category or "未知",
                    "revenue_cents": int(row.revenue_cents),
                    "revenue": _money(int(row.revenue_cents)),
                    "order_count": int(row.order_count),
                }
                for row in rows
            ],
        }

    def product_revenue(
        self,
        product_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        start_date, end_date = self._resolved_range(start_date, end_date)
        normalized = product_name.lower().replace(" ", "")
        products = self.session.scalars(select(Product).order_by(Product.product_id)).all()
        exact = [
            product
            for product in products
            if product.product_name.lower().replace(" ", "") == normalized
        ]
        matches = exact or [
            product
            for product in products
            if normalized in product.product_name.lower().replace(" ", "")
            or product.product_name.lower().replace(" ", "") in normalized
        ]
        if not matches:
            return {
                "status": "not_found",
                "product_name": product_name,
                "period": {"start_date": start_date, "end_date": end_date},
            }
        if len(matches) > 1:
            return {
                "status": "ambiguous",
                "product_name": product_name,
                "candidates": [product.product_name for product in matches],
                "period": {"start_date": start_date, "end_date": end_date},
            }

        product = matches[0]
        revenue, orders, qty = self.session.execute(
            select(
                func.coalesce(func.sum(Sale.amount_cents), 0),
                func.count(distinct(Sale.order_id)),
                func.coalesce(func.sum(Sale.qty), 0),
            ).where(
                *self._filters(start_date, end_date),
                Sale.product_id == product.product_id,
            )
        ).one()
        revenue_cents = int(revenue or 0)
        return {
            "status": "ok",
            "product_id": product.product_id,
            "product_name": product.product_name,
            "product_category": product.product_category,
            "period": {"start_date": start_date, "end_date": end_date},
            "revenue_cents": revenue_cents,
            "revenue": _money(revenue_cents),
            "order_count": int(orders or 0),
            "qty": int(qty or 0),
        }

    def compare_recent_monthly_aov(self) -> dict[str, Any]:
        _, max_date = self.dataset_range()
        current_start = max_date.replace(day=1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        current_end = date(
            current_start.year,
            current_start.month,
            monthrange(current_start.year, current_start.month)[1],
        )
        current_end = min(current_end, max_date)
        current = self._summary(current_start, current_end)
        previous = self._summary(previous_start, previous_end)
        change_pct = _percentage_change(current["aov_cents"], previous["aov_cents"])
        direction = (
            "up"
            if current["aov_cents"] > previous["aov_cents"]
            else "down"
            if current["aov_cents"] < previous["aov_cents"]
            else "flat"
        )
        return {
            "current": {
                "start_date": current_start,
                "end_date": current_end,
                **current,
            },
            "previous": {
                "start_date": previous_start,
                "end_date": previous_end,
                **previous,
            },
            "direction": direction,
            "change_pct": change_pct,
        }

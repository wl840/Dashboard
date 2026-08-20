from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import DataQualityIssue, ImportRun, Product, RawSale, Sale, Store

DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y")


@dataclass(frozen=True)
class ImportSummary:
    dataset_hash: str
    raw_rows: int
    canonical_orders: int
    valid_orders: int
    issue_count: int
    reused: bool = False


@dataclass(frozen=True)
class Issue:
    source_row: int | None
    order_id: str | None
    code: str
    severity: str
    detail: str


@dataclass
class Candidate:
    source_row: int
    raw: dict[str, str]
    order_id: str
    sale_date: date | None
    store_id: str | None
    product_id: str | None
    qty: int | None
    amount_cents: int | None
    payment: str
    formula_matches: bool
    issues: list[Issue] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(
            (
                2 if self.sale_date is not None else 0,
                2 if self.amount_cents is not None else 0,
                2 if self.amount_cents is not None and self.amount_cents > 0 else 0,
                2 if self.qty is not None and self.qty > 0 else 0,
                1 if self.store_id and self.store_id.startswith("S") else 0,
                1 if self.product_id and self.product_id.startswith("P") else 0,
                3 if self.formula_matches else 0,
            )
        )

    @property
    def raw_signature(self) -> tuple[str, ...]:
        return tuple(self.raw.values())

    @property
    def normalized_signature(self) -> tuple[object, ...]:
        return (
            self.order_id,
            self.sale_date,
            self.store_id,
            self.product_id,
            self.qty,
            self.amount_cents,
            self.payment,
        )


def _read_csv(path: Path, expected_columns: set[str]) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required source file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        if not expected_columns.issubset(columns):
            missing = ", ".join(sorted(expected_columns - columns))
            raise ValueError(f"{path.name} is missing required columns: {missing}")
        return list(reader)


def _dataset_hash(source_dir: Path) -> str:
    digest = hashlib.sha256()
    for filename in ("stores.csv", "products.csv", "sales.csv"):
        path = source_dir / filename
        digest.update(filename.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _parse_date(value: str) -> tuple[date | None, str | None]:
    normalized = value.strip()
    for date_format in DATE_FORMATS:
        try:
            parsed = datetime.strptime(normalized, date_format).date()
            return parsed, None if date_format == "%Y-%m-%d" else date_format
        except ValueError:
            continue
    return None, None


def _parse_amount(value: str) -> tuple[int | None, bool]:
    normalized = value.strip()
    if not normalized:
        return None, False
    cleaned = normalized.replace("¥", "").replace("￥", "").replace(",", "").strip()
    try:
        decimal_amount = Decimal(cleaned)
    except InvalidOperation:
        return None, cleaned != normalized
    cents = decimal_amount * 100
    if cents != cents.to_integral_value():
        return None, cleaned != normalized
    return int(cents), cleaned != normalized


def _parse_qty(value: str) -> int | None:
    try:
        return int(value.strip())
    except ValueError:
        return None


def _issue(candidate: Candidate, code: str, severity: str, detail: str) -> None:
    candidate.issues.append(
        Issue(candidate.source_row, candidate.order_id, code, severity, detail)
    )


def _candidate(
    raw: dict[str, str],
    source_row: int,
    store_ids: set[str],
    product_prices: dict[str, int],
) -> Candidate:
    order_id = raw["order_id"].strip()
    sale_date, date_format = _parse_date(raw["date"])
    store_id = raw["store_id"].strip().upper() or None
    product_id = raw["product_id"].strip().upper() or None
    qty = _parse_qty(raw["qty"])
    amount_cents, amount_normalized = _parse_amount(raw["amount"])
    candidate = Candidate(
        source_row=source_row,
        raw=raw,
        order_id=order_id,
        sale_date=sale_date,
        store_id=store_id,
        product_id=product_id,
        qty=qty,
        amount_cents=amount_cents,
        payment=raw["payment"].strip(),
        formula_matches=(
            amount_cents is not None
            and qty is not None
            and product_id in product_prices
            and amount_cents == qty * product_prices[product_id]
        ),
    )

    if sale_date is None:
        _issue(candidate, "invalid_date", "error", f"无法解析日期：{raw['date']}")
    elif date_format:
        _issue(candidate, "date_normalized", "info", f"日期格式由 {date_format} 规范化")
    if raw["store_id"] != (store_id or ""):
        _issue(candidate, "store_id_normalized", "info", "门店 ID 已去空格并转为大写")
    if store_id not in store_ids:
        _issue(candidate, "unknown_store", "warning", f"门店维表中不存在 {store_id}")
    if product_id not in product_prices:
        _issue(candidate, "unknown_product", "warning", f"商品维表中不存在 {product_id}")
    if not raw["amount"].strip():
        _issue(candidate, "missing_amount", "error", "金额为空")
    elif amount_cents is None:
        _issue(candidate, "invalid_amount", "error", f"无法解析金额：{raw['amount']}")
    elif amount_normalized:
        _issue(candidate, "amount_normalized", "info", "金额中的币种符号或分隔符已移除")
    if amount_cents is not None and amount_cents <= 0:
        _issue(candidate, "nonpositive_amount", "error", f"金额为 {amount_cents / 100:.2f}")
    if qty is None:
        _issue(candidate, "invalid_qty", "error", f"无法解析数量：{raw['qty']}")
    elif qty <= 0:
        _issue(candidate, "nonpositive_qty", "error", f"数量为 {qty}")
    return candidate


def _summary_from_run(run: ImportRun, reused: bool) -> ImportSummary:
    return ImportSummary(
        dataset_hash=run.dataset_hash,
        raw_rows=run.raw_rows,
        canonical_orders=run.canonical_orders,
        valid_orders=run.valid_orders,
        issue_count=run.issue_count,
        reused=reused,
    )


def ensure_data_loaded(session: Session, source_dir: Path) -> ImportSummary:
    current_hash = _dataset_hash(source_dir)
    latest_run = session.scalar(select(ImportRun).order_by(ImportRun.id.desc()).limit(1))
    canonical_count = session.scalar(select(func.count()).select_from(Sale)) or 0
    if latest_run and latest_run.dataset_hash == current_hash and canonical_count:
        return _summary_from_run(latest_run, reused=True)

    stores = _read_csv(
        source_dir / "stores.csv",
        {"store_id", "store_name", "category", "district"},
    )
    products = _read_csv(
        source_dir / "products.csv",
        {"product_id", "product_name", "product_category", "unit_price"},
    )
    raw_sales = _read_csv(
        source_dir / "sales.csv",
        {"order_id", "date", "store_id", "product_id", "qty", "amount", "payment"},
    )

    store_mappings = [
        {
            "store_id": row["store_id"].strip().upper(),
            "store_name": row["store_name"].strip(),
            "category": row["category"].strip(),
            "district": row["district"].strip(),
        }
        for row in stores
    ]
    product_mappings = [
        {
            "product_id": row["product_id"].strip().upper(),
            "product_name": row["product_name"].strip(),
            "product_category": row["product_category"].strip(),
            "unit_price_cents": int(Decimal(row["unit_price"].strip()) * 100),
        }
        for row in products
    ]
    store_ids = {row["store_id"] for row in store_mappings}
    product_prices = {
        row["product_id"]: row["unit_price_cents"] for row in product_mappings
    }

    candidates_by_order: dict[str, list[Candidate]] = defaultdict(list)
    raw_mappings: list[dict[str, object]] = []
    all_issues: list[Issue] = []
    for source_row, raw in enumerate(raw_sales, start=2):
        candidate = _candidate(raw, source_row, store_ids, product_prices)
        candidates_by_order[candidate.order_id].append(candidate)
        all_issues.extend(candidate.issues)
        raw_mappings.append(
            {
                "source_row": source_row,
                "order_id": raw["order_id"],
                "raw_date": raw["date"],
                "raw_store_id": raw["store_id"],
                "raw_product_id": raw["product_id"],
                "raw_qty": raw["qty"],
                "raw_amount": raw["amount"] or None,
                "raw_payment": raw["payment"],
            }
        )

    sale_mappings: list[dict[str, object]] = []
    for order_id, group in candidates_by_order.items():
        selected = min(group, key=lambda item: (-item.score, item.source_row))
        group_flags = {issue.code for issue in selected.issues}
        if len(group) > 1:
            for duplicate in group:
                if duplicate.source_row == selected.source_row:
                    continue
                if duplicate.raw_signature == selected.raw_signature:
                    code, detail = "duplicate_exact", "与保留记录完全重复"
                elif duplicate.normalized_signature == selected.normalized_signature:
                    code, detail = "duplicate_normalized", "规范化后与保留记录重复"
                else:
                    code, detail = "duplicate_conflict", "同一订单存在字段冲突"
                all_issues.append(
                    Issue(duplicate.source_row, order_id, code, "warning", detail)
                )
                group_flags.add(code)

            distinct_stores = {candidate.store_id for candidate in group}
            if len(distinct_stores) > 1:
                selected.store_id = None
                all_issues.append(
                    Issue(
                        selected.source_row,
                        order_id,
                        "duplicate_store_conflict",
                        "error",
                        "重复订单的门店归属冲突，规范表中归入未知门店",
                    )
                )
                group_flags.add("duplicate_store_conflict")

        is_valid = bool(
            selected.sale_date is not None
            and selected.amount_cents is not None
            and selected.amount_cents > 0
            and selected.qty is not None
            and selected.qty > 0
        )
        if not is_valid:
            all_issues.append(
                Issue(
                    selected.source_row,
                    order_id,
                    "excluded_from_metrics",
                    "error",
                    "关键金额、数量或日期无效，已从经营指标中排除",
                )
            )
            group_flags.add("excluded_from_metrics")

        sale_mappings.append(
            {
                "order_id": order_id,
                "sale_date": selected.sale_date,
                "store_id": selected.store_id,
                "product_id": selected.product_id,
                "qty": selected.qty,
                "amount_cents": selected.amount_cents,
                "payment": selected.payment,
                "source_row": selected.source_row,
                "is_valid": is_valid,
                "quality_flags": json.dumps(sorted(group_flags), ensure_ascii=False),
            }
        )

    issue_mappings = [
        {
            "source_row": issue.source_row,
            "order_id": issue.order_id,
            "code": issue.code,
            "severity": issue.severity,
            "detail": issue.detail,
        }
        for issue in all_issues
    ]
    valid_orders = sum(1 for row in sale_mappings if row["is_valid"])

    try:
        for model in (DataQualityIssue, Sale, RawSale, Product, Store, ImportRun):
            session.execute(delete(model))
        session.bulk_insert_mappings(Store, store_mappings)
        session.bulk_insert_mappings(Product, product_mappings)
        session.bulk_insert_mappings(RawSale, raw_mappings)
        session.bulk_insert_mappings(Sale, sale_mappings)
        session.bulk_insert_mappings(DataQualityIssue, issue_mappings)
        run = ImportRun(
            dataset_hash=current_hash,
            imported_at=datetime.now(UTC).replace(tzinfo=None),
            raw_rows=len(raw_mappings),
            canonical_orders=len(sale_mappings),
            valid_orders=valid_orders,
            issue_count=len(issue_mappings),
        )
        session.add(run)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return _summary_from_run(run, reused=False)

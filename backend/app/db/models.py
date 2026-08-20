from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Store(Base):
    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    store_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(80))
    district: Mapped[str] = mapped_column(String(120))


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(120), index=True)
    product_category: Mapped[str] = mapped_column(String(80), index=True)
    unit_price_cents: Mapped[int] = mapped_column(Integer)


class RawSale(Base):
    __tablename__ = "sales_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_row: Mapped[int] = mapped_column(Integer, unique=True)
    order_id: Mapped[str] = mapped_column(String(32), index=True)
    raw_date: Mapped[str] = mapped_column(String(32))
    raw_store_id: Mapped[str] = mapped_column(String(32))
    raw_product_id: Mapped[str] = mapped_column(String(32))
    raw_qty: Mapped[str] = mapped_column(String(32))
    raw_amount: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payment: Mapped[str] = mapped_column(String(64))


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (
        Index("ix_sales_date_store", "sale_date", "store_id"),
        Index("ix_sales_date_product", "sale_date", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    store_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment: Mapped[str] = mapped_column(String(64))
    source_row: Mapped[int] = mapped_column(Integer)
    is_valid: Mapped[bool] = mapped_column(Boolean, index=True)
    quality_flags: Mapped[str] = mapped_column(Text, default="[]")


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    __table_args__ = (Index("ix_quality_code_severity", "code", "severity"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(Text)


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_hash: Mapped[str] = mapped_column(String(64), unique=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime)
    raw_rows: Mapped[int] = mapped_column(Integer)
    canonical_orders: Mapped[int] = mapped_column(Integer)
    valid_orders: Mapped[int] = mapped_column(Integer)
    issue_count: Mapped[int] = mapped_column(Integer)

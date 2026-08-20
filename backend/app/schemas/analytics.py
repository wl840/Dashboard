from datetime import date, datetime

from pydantic import BaseModel, Field


class DateRange(BaseModel):
    start_date: date
    end_date: date


class SummaryMetric(BaseModel):
    revenue_cents: int = Field(description="营业额，单位为人民币分")
    revenue: str
    order_count: int
    aov_cents: int = Field(description="客单价，单位为人民币分")
    aov: str
    revenue_change_pct: float | None = None
    orders_change_pct: float | None = None
    aov_change_pct: float | None = None


class DailyMetric(BaseModel):
    date: date
    revenue_cents: int
    order_count: int
    aov_cents: int


class ProductMetric(BaseModel):
    rank: int
    product_id: str
    product_name: str
    product_category: str
    revenue_cents: int
    revenue: str
    order_count: int
    qty: int


class StoreMetric(BaseModel):
    store_id: str
    store_name: str
    category: str
    revenue_cents: int
    revenue: str
    order_count: int
    aov_cents: int


class QualityCompact(BaseModel):
    raw_rows: int
    canonical_orders: int
    valid_orders: int
    excluded_orders: int
    coverage_pct: float
    issue_count: int
    dataset_hash: str
    imported_at: datetime


class DashboardResponse(BaseModel):
    range: DateRange
    filters: dict[str, str | None]
    summary: SummaryMetric
    daily: list[DailyMetric]
    top_products: list[ProductMetric]
    store_performance: list[StoreMetric]
    quality: QualityCompact


class StoreOption(BaseModel):
    store_id: str
    store_name: str
    category: str
    district: str


class ProductOption(BaseModel):
    product_id: str
    product_name: str
    product_category: str


class MetadataResponse(BaseModel):
    date_range: DateRange
    stores: list[StoreOption]
    products: list[ProductOption]

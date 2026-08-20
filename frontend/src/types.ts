export interface DateRange {
  start_date: string;
  end_date: string;
}

export interface StoreOption {
  store_id: string;
  store_name: string;
  category: string;
  district: string;
}

export interface ProductOption {
  product_id: string;
  product_name: string;
  product_category: string;
}

export interface Metadata {
  date_range: DateRange;
  stores: StoreOption[];
  products: ProductOption[];
}

export interface SummaryMetric {
  revenue_cents: number;
  revenue: string;
  order_count: number;
  aov_cents: number;
  aov: string;
  revenue_change_pct: number | null;
  orders_change_pct: number | null;
  aov_change_pct: number | null;
}

export interface DailyMetric {
  date: string;
  revenue_cents: number;
  order_count: number;
  aov_cents: number;
}

export interface ProductMetric {
  rank: number;
  product_id: string;
  product_name: string;
  product_category: string;
  revenue_cents: number;
  revenue: string;
  order_count: number;
  qty: number;
}

export interface StoreMetric {
  store_id: string;
  store_name: string;
  category: string;
  revenue_cents: number;
  revenue: string;
  order_count: number;
  aov_cents: number;
}

export interface QualitySnapshot {
  raw_rows: number;
  canonical_orders: number;
  valid_orders: number;
  excluded_orders: number;
  coverage_pct: number;
  issue_count: number;
  dataset_hash: string;
  imported_at: string;
}

export interface DashboardData {
  range: DateRange;
  filters: { store_id: string | null };
  summary: SummaryMetric;
  daily: DailyMetric[];
  top_products: ProductMetric[];
  store_performance: StoreMetric[];
  quality: QualitySnapshot;
}

export interface DashboardFilters {
  startDate: string;
  endDate: string;
  storeId: string;
}

export interface ChatEvidence {
  source: string;
  tool: string;
  parameters: Record<string, unknown>;
  result: Record<string, unknown>;
  metric_policy: string;
  coverage: {
    valid_orders: number;
    canonical_orders: number;
    coverage_pct: number;
  };
}

export interface ChartAction {
  type: "apply_date_range";
  start_date: string;
  end_date: string;
  highlight_product_id?: string;
}

export interface ChatResponse {
  answer: string;
  provider: string;
  tool_name: string | null;
  context: Record<string, unknown>;
  evidence: ChatEvidence | null;
  chart_action: ChartAction | null;
  fallback_reason: string | null;
}

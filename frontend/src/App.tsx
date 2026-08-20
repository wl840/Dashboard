import {
  Activity,
  BarChart3,
  Bot,
  Calendar,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Database,
  LayoutDashboard,
  Package,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Store,
  TrendingUp,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchDashboard, fetchMetadata, sendChat } from "./api";
import type {
  ChartAction,
  ChatEvidence,
  DashboardData,
  DashboardFilters,
  Metadata,
} from "./types";

const moneyFormatter = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  minimumFractionDigits: 2,
});
const integerFormatter = new Intl.NumberFormat("zh-CN");
const compactFormatter = new Intl.NumberFormat("zh-CN", {
  notation: "compact",
  maximumFractionDigits: 1,
});

function formatMoney(cents: number): string {
  return moneyFormatter.format(cents / 100);
}

function formatShortDate(value: string): string {
  const [, month, day] = value.split("-");
  return `${month}/${day}`;
}

function formatDisplayDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${year}.${month}.${day}`;
}

function offsetDate(value: string, days: number): string {
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function monthStart(value: string): string {
  return `${value.slice(0, 7)}-01`;
}

function ChangeBadge({ value, fallback }: { value: number | null; fallback: string }) {
  if (value === null) {
    return <span className="metric-context neutral">{fallback}</span>;
  }
  const positive = value >= 0;
  return (
    <span className={`metric-context ${positive ? "positive" : "negative"}`}>
      <TrendingUp size={13} className={positive ? "" : "trend-down"} />
      {positive ? "+" : ""}
      {value.toFixed(1)}% 较上周期
    </span>
  );
}

interface KpiCardProps {
  label: string;
  value: string;
  helper: string;
  change: number | null;
  icon: LucideIcon;
  tone: "dark" | "lime" | "coral" | "plain";
}

function KpiCard({
  label,
  value,
  helper,
  change,
  icon: Icon,
  tone,
}: KpiCardProps) {
  return (
    <article className={`kpi-card tone-${tone}`}>
      <div className="kpi-topline">
        <span>{label}</span>
        <span className="kpi-icon">
          <Icon size={18} />
        </span>
      </div>
      <strong>{value}</strong>
      <div className="kpi-footer">
        <ChangeBadge value={change} fallback={helper} />
      </div>
    </article>
  );
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  evidence?: ChatEvidence | null;
  action?: ChartAction | null;
}

const TOOL_LABELS: Record<string, string> = {
  rank_store_categories: "门店品类排行",
  get_product_revenue: "商品销售查询",
  compare_recent_monthly_aov: "月度客单价对比",
  get_period_summary: "经营指标汇总",
};

function EvidenceCard({
  evidence,
  action,
  onAction,
}: {
  evidence: ChatEvidence;
  action?: ChartAction | null;
  onAction: (action: ChartAction) => void;
}) {
  return (
    <div className="evidence-card">
      <div className="evidence-title">
        <ShieldCheck size={15} />
        <span>计算依据</span>
        <span className="verified-pill">已核验</span>
      </div>
      <div className="evidence-grid">
        <div>
          <span>查询工具</span>
          <strong>{TOOL_LABELS[evidence.tool] ?? evidence.tool}</strong>
        </div>
        <div>
          <span>数据覆盖</span>
          <strong>{evidence.coverage.coverage_pct.toFixed(1)}%</strong>
        </div>
        <div>
          <span>有效订单</span>
          <strong>{integerFormatter.format(evidence.coverage.valid_orders)}</strong>
        </div>
        <div>
          <span>数据源</span>
          <strong>SQLite</strong>
        </div>
      </div>
      <details>
        <summary>查看查询结果与口径</summary>
        <p>{evidence.metric_policy}</p>
        <pre>{JSON.stringify(evidence.result, null, 2)}</pre>
      </details>
      {action && (
        <button className="sync-button" type="button" onClick={() => onAction(action)}>
          同步到看板 <ChevronRight size={15} />
        </button>
      )}
    </div>
  );
}

function ChatPanel({ onChartAction }: { onChartAction: (action: ChartAction) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "你好，我是 Pulse AI。你可以问我门店、商品、营业额或客单价；回答中的数字都会实时查询 SQLite。",
    },
  ]);
  const [context, setContext] = useState<Record<string, unknown>>({});
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, sending]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || sending) return;
    setInput("");
    setMessages((current) => [
      ...current,
      { id: `${Date.now()}-user`, role: "user", content: trimmed },
    ]);
    setSending(true);
    try {
      const response = await sendChat(trimmed, context);
      setContext(response.context);
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content: response.answer,
          evidence: response.evidence,
          action: response.chart_action,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: `${Date.now()}-error`,
          role: "assistant",
          content:
            error instanceof Error
              ? `查询失败：${error.message}`
              : "查询失败，请稍后重试。",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <aside className="chat-card">
      <div className="card-heading chat-heading">
        <div>
          <span className="section-kicker">
            <Sparkles size={14} /> GROUNDED AI
          </span>
          <h2>问问经营数据</h2>
        </div>
        <span className="online-dot">在线</span>
      </div>
      <div className="suggestion-row">
        {["哪个门店品类营业额最高？", "牛肉poke 六月卖了多少？", "客单价最近涨了吗？"].map(
          (question) => (
            <button key={question} type="button" onClick={() => void ask(question)}>
              {question}
            </button>
          ),
        )}
      </div>
      <div className="chat-messages" ref={scrollRef}>
        {messages.map((message) => (
          <div key={message.id} className={`message-row ${message.role}`}>
            {message.role === "assistant" && (
              <span className="assistant-avatar">
                <Bot size={16} />
              </span>
            )}
            <div className="message-stack">
              <div className="message-bubble">{message.content}</div>
              {message.evidence && (
                <EvidenceCard
                  evidence={message.evidence}
                  action={message.action}
                  onAction={onChartAction}
                />
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div className="message-row assistant">
            <span className="assistant-avatar">
              <Bot size={16} />
            </span>
            <div className="thinking">
              <span />
              <span />
              <span />
              正在查询数据库
            </div>
          </div>
        )}
      </div>
      <form
        className="chat-input"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(input);
        }}
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="例如：那五月呢？"
          aria-label="向 Pulse AI 提问"
        />
        <button type="submit" disabled={!input.trim() || sending} aria-label="发送">
          <Send size={17} />
        </button>
      </form>
      <p className="ai-disclaimer">
        <ShieldCheck size={13} /> 数字由受控查询工具生成，AI 不直接编写 SQL
      </p>
    </aside>
  );
}

function App() {
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [filters, setFilters] = useState<DashboardFilters | null>(null);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [highlightProductId, setHighlightProductId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchMetadata(controller.signal)
      .then((result) => {
        setMetadata(result);
        setFilters({
          startDate: result.date_range.start_date,
          endDate: result.date_range.end_date,
          storeId: "",
        });
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法加载数据范围");
        setLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!filters) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchDashboard(filters, controller.signal)
      .then(setDashboard)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法加载看板");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [filters, revision]);

  const trendData = useMemo(
    () =>
      dashboard?.daily.map((row) => ({
        date: row.date,
        revenue: row.revenue_cents / 100,
        orders: row.order_count,
      })) ?? [],
    [dashboard],
  );

  function applyPreset(preset: "all" | "30d" | "month") {
    if (!metadata) return;
    const endDate = metadata.date_range.end_date;
    setFilters((current) => ({
      startDate:
        preset === "all"
          ? metadata.date_range.start_date
          : preset === "30d"
            ? offsetDate(endDate, -29)
            : monthStart(endDate),
      endDate,
      storeId: current?.storeId ?? "",
    }));
  }

  function applyChartAction(action: ChartAction) {
    setFilters((current) => ({
      startDate: action.start_date,
      endDate: action.end_date,
      storeId: current?.storeId ?? "",
    }));
    setHighlightProductId(action.highlight_product_id ?? null);
    document.querySelector(".trend-card")?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }

  if (!metadata || !filters || !dashboard) {
    return (
      <main className="initial-loader">
        <span className="loader-logo">
          <Activity size={24} />
        </span>
        <strong>Moneki Pulse</strong>
        <p>{error ?? "正在校验并载入经营数据…"}</p>
      </main>
    );
  }

  const topRevenue = dashboard.top_products[0]?.revenue_cents ?? 1;

  return (
    <div className="app-shell">
      <nav className="side-nav" aria-label="主导航">
        <div className="nav-brand">
          <Activity size={23} />
        </div>
        <div className="nav-links">
          <button className="active" type="button" aria-label="经营看板">
            <LayoutDashboard size={20} />
          </button>
          <button type="button" aria-label="趋势分析">
            <BarChart3 size={20} />
          </button>
          <button type="button" aria-label="AI 助手">
            <Bot size={20} />
          </button>
          <button type="button" aria-label="数据质量">
            <Database size={20} />
          </button>
        </div>
        <div className="nav-avatar">WL</div>
      </nav>

      <main className="dashboard-main">
        <header className="topbar">
          <div>
            <span className="breadcrumb">经营中心 / 实时总览</span>
            <h1>早上好，来看今天的经营脉搏。</h1>
          </div>
          <div className="topbar-status">
            <span>
              <CheckCircle2 size={15} /> 数据已核验
            </span>
            <button
              type="button"
              onClick={() => setRevision((value) => value + 1)}
              disabled={loading}
              aria-label="刷新数据"
            >
              <RefreshCw size={17} className={loading ? "spin" : ""} />
            </button>
          </div>
        </header>

        <section className="filter-bar">
          <div className="preset-tabs">
            <button type="button" onClick={() => applyPreset("all")}>全部周期</button>
            <button type="button" onClick={() => applyPreset("30d")}>近 30 天</button>
            <button type="button" onClick={() => applyPreset("month")}>最近一月</button>
          </div>
          <label className="field-control">
            <Calendar size={16} />
            <input
              type="date"
              min={metadata.date_range.start_date}
              max={filters.endDate}
              value={filters.startDate}
              onChange={(event) => setFilters({ ...filters, startDate: event.target.value })}
              aria-label="开始日期"
            />
            <span>至</span>
            <input
              type="date"
              min={filters.startDate}
              max={metadata.date_range.end_date}
              value={filters.endDate}
              onChange={(event) => setFilters({ ...filters, endDate: event.target.value })}
              aria-label="结束日期"
            />
          </label>
          <label className="field-control store-filter">
            <Store size={16} />
            <select
              value={filters.storeId}
              onChange={(event) => setFilters({ ...filters, storeId: event.target.value })}
              aria-label="门店筛选"
            >
              <option value="">全部门店</option>
              {metadata.stores.map((store) => (
                <option key={store.store_id} value={store.store_id}>
                  {store.store_name}
                </option>
              ))}
            </select>
          </label>
        </section>

        {error && <div className="error-banner">{error}</div>}

        <section className="kpi-grid">
          <KpiCard
            label="营业额"
            value={formatMoney(dashboard.summary.revenue_cents)}
            helper={`${formatDisplayDate(filters.startDate)} 起`}
            change={dashboard.summary.revenue_change_pct}
            icon={CircleDollarSign}
            tone="dark"
          />
          <KpiCard
            label="有效订单"
            value={integerFormatter.format(dashboard.summary.order_count)}
            helper="去重后订单"
            change={dashboard.summary.orders_change_pct}
            icon={Users}
            tone="lime"
          />
          <KpiCard
            label="客单价"
            value={formatMoney(dashboard.summary.aov_cents)}
            helper="营业额 / 订单数"
            change={dashboard.summary.aov_change_pct}
            icon={TrendingUp}
            tone="coral"
          />
          <KpiCard
            label="数据覆盖率"
            value={`${dashboard.quality.coverage_pct.toFixed(1)}%`}
            helper={`排除 ${dashboard.quality.excluded_orders} 笔异常`}
            change={null}
            icon={ShieldCheck}
            tone="plain"
          />
        </section>

        <section className="workspace-grid">
          <article className="panel-card trend-card">
            <div className="card-heading">
              <div>
                <span className="section-kicker">REVENUE PULSE</span>
                <h2>营业额趋势</h2>
              </div>
              <div className="chart-total">
                <span>区间总额</span>
                <strong>{formatMoney(dashboard.summary.revenue_cents)}</strong>
              </div>
            </div>
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData} margin={{ top: 14, right: 4, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#d8f75a" stopOpacity={0.42} />
                      <stop offset="100%" stopColor="#d8f75a" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#e9e8e1" strokeDasharray="3 5" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatShortDate}
                    axisLine={false}
                    tickLine={false}
                    minTickGap={32}
                    tick={{ fill: "#7d8883", fontSize: 11 }}
                  />
                  <YAxis
                    tickFormatter={(value: number) => `¥${compactFormatter.format(value)}`}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#7d8883", fontSize: 11 }}
                  />
                  <Tooltip
                    formatter={(value) => [moneyFormatter.format(Number(value)), "营业额"]}
                    labelFormatter={(label) => formatDisplayDate(String(label))}
                    contentStyle={{
                      border: "0",
                      borderRadius: 14,
                      boxShadow: "0 14px 40px rgba(15, 30, 25, .16)",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="revenue"
                    stroke="#6e871e"
                    strokeWidth={2.5}
                    fill="url(#revenueFill)"
                    activeDot={{ r: 5, fill: "#101c1a", stroke: "#d8f75a", strokeWidth: 3 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-footnote">
              <Activity size={14} />
              共覆盖 {dashboard.daily.length} 天，所有日汇总与区间总额已自动回勾
            </div>
          </article>

          <ChatPanel onChartAction={applyChartAction} />
        </section>

        <section className="lower-grid">
          <article className="panel-card products-card">
            <div className="card-heading">
              <div>
                <span className="section-kicker">PRODUCT RANKING</span>
                <h2>Top 10 商品</h2>
              </div>
              <span className="table-note">按营业额排序</span>
            </div>
            <div className="product-table">
              <div className="product-row table-header">
                <span>排名 / 商品</span>
                <span>品类</span>
                <span>销量</span>
                <span>营业额</span>
              </div>
              {dashboard.top_products.map((product) => (
                <div
                  className={`product-row ${
                    highlightProductId === product.product_id ? "highlighted" : ""
                  }`}
                  key={product.product_id}
                >
                  <div className="product-name-cell">
                    <span className="rank">{String(product.rank).padStart(2, "0")}</span>
                    <span className="product-icon">
                      <Package size={16} />
                    </span>
                    <div>
                      <strong>{product.product_name}</strong>
                      <small>{product.product_id}</small>
                    </div>
                  </div>
                  <span className="category-pill">{product.product_category}</span>
                  <span>{integerFormatter.format(product.qty)} 份</span>
                  <div className="revenue-cell">
                    <strong>{formatMoney(product.revenue_cents)}</strong>
                    <span>
                      <i
                        style={{
                          width: `${Math.max(
                            8,
                            (product.revenue_cents / topRevenue) * 100,
                          )}%`,
                        }}
                      />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </article>

          <article className="panel-card stores-card">
            <div className="card-heading">
              <div>
                <span className="section-kicker">STORE MIX</span>
                <h2>门店贡献</h2>
              </div>
              <Store size={19} />
            </div>
            <div className="store-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={dashboard.store_performance}
                  layout="vertical"
                  margin={{ top: 4, right: 12, left: 12, bottom: 2 }}
                >
                  <XAxis type="number" hide />
                  <YAxis
                    dataKey="store_name"
                    type="category"
                    width={112}
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: "#52605b", fontSize: 11 }}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(216, 247, 90, .12)" }}
                    formatter={(value) => [formatMoney(Number(value)), "营业额"]}
                    contentStyle={{
                      border: "0",
                      borderRadius: 14,
                      boxShadow: "0 14px 40px rgba(15, 30, 25, .16)",
                    }}
                  />
                  <Bar dataKey="revenue_cents" radius={[0, 8, 8, 0]} barSize={18}>
                    {dashboard.store_performance.map((store, index) => (
                      <Cell
                        key={store.store_id}
                        fill={index === 0 ? "#101c1a" : index === 1 ? "#ddf36c" : "#cbd3ce"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="quality-strip">
              <span className="quality-icon">
                <Database size={16} />
              </span>
              <div>
                <strong>{integerFormatter.format(dashboard.quality.issue_count)} 条</strong>
                <small>清洗事件均保留审计记录</small>
              </div>
              <ShieldCheck size={18} />
            </div>
          </article>
        </section>

        <footer>
          <span>Moneki Pulse · 数据集 {dashboard.quality.dataset_hash}</span>
          <span>
            <ShieldCheck size={13} /> Trusted analytics by design
          </span>
        </footer>
      </main>
    </div>
  );
}

export default App;

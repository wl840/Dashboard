# Moneki Pulse

面向连锁餐饮运营的销售数据看板与可信 AI 数据问答。项目使用 FastAPI、React 和 SQLite，将原始 POS CSV 清洗为可审计的销售事实表；看板和 AI 共用同一个查询仓库，因此每个回答都能回溯到真实数据库结果。

## 3 步运行

1. **git clone https://github.com/wl840/Dashboard.git && cd Dashboard**
2. **docker compose up --build**
3. 打开 <http://localhost:8080>，API 文档位于 <http://localhost:8000/docs>

默认使用无需密钥的 mock 意图解析器，但查询工具、SQLite 取数和答案证据链都是真实的。

## 已实现

- 日期区间与门店筛选
- 营业额、订单数、客单价及同周期变化
- 每日营业额趋势、Top 10 商品和门店贡献
- 原始数据、规范事实表和 708 条数据质量审计事件
- 自然语言查询门店品类、商品营业额、区间指标和客单价趋势
- 对话追问，例如先问“牛肉 poke 六月”，再问“那五月呢？”
- AI 答案证据卡和一键同步看板
- 不可回答问题的明确兜底
- 真实数据库基线与 AI 数字一致性测试

## 架构

~~~mermaid
flowchart LR
    CSV[POS CSV] --> Import[幂等导入与质量检查]
    Import --> Raw[(sales_raw)]
    Import --> Fact[(canonical sales)]
    Fact --> Repo[Analytics Repository]
    Repo --> API[Dashboard API]
    Repo --> Tools[Allowlisted AI Tools]
    Planner[LLM / Mock Planner] --> Tools
    Tools --> Evidence[确定性答案 + Evidence]
    API --> React[React Dashboard]
    Evidence --> React
~~~

关键设计是 AnalyticsRepository：看板 API 与 AI 工具不各写一套 SQL，而是调用同一查询层。

## 数据口径

原始数据保留在 sales_raw，规范数据写入 sales，所有修改原因写入 data_quality_issues。

| 问题 | 处理 |
|---|---|
| 三种日期格式 | 统一解析为 DATE |
| ¥ 金额 | 去符号后转换为整数分 |
| 完全重复订单 | 保留一条并记录审计事件 |
| 冲突重复订单 | 按数据完整性和金额/单价一致性择优 |
| 门店归属冲突 | 归入“未知门店”，不猜测 |
| s01、S01 加空格 | 去空格并转大写 |
| S99、P99 | 保留金额，维度显示为未知 |
| 金额缺失、金额非正或数量非正 | 从必做经营指标中排除并保留原始记录 |

指标定义：

- 营业额：有效订单的 SUM(amount_cents)
- 订单数：同一有效集的 COUNT(DISTINCT order_id)
- 客单价：营业额 ÷ 订单数，四舍五入到分
- 日期区间首尾均包含

全量基线：

| 指标 | 结果 |
|---|---:|
| 原始记录 | 12,131 |
| 规范订单 | 12,051 |
| 有效订单 | 11,858 |
| 营业额 | ¥426,601.00 |
| 客单价 | ¥35.98 |
| 数据覆盖率 | 98.4% |

## 可信 AI 链路

~~~text
用户问题
  → 模型只选择允许的工具和参数
  → FastAPI 校验参数
  → AnalyticsRepository 查询 SQLite
  → 服务端用查询结果确定性填充数字
  → 返回 answer + evidence + chart_action
~~~

模型不会接收 CSV 原文、不能执行任意 SQL，也不负责填写最终数字。即使外部模型不可用，系统会降级到 mock 意图解析器，但仍然使用真实查询工具。

支持的工具：

- rank_store_categories
- get_product_revenue
- compare_recent_monthly_aov
- get_period_summary

接入兼容 Chat Completions 工具调用的模型时，在 .env 中配置：

~~~dotenv
AI_PROVIDER=openai_compatible
AI_API_KEY=your-key
AI_BASE_URL=https://your-provider.example/v1
AI_MODEL=your-tool-capable-model
~~~

不要把 .env 或密钥提交到 Git。

## 本地开发

后端：

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
~~~

前端：

~~~powershell
Set-Location frontend
npm install
npm run dev
~~~

SQLite 会在首次启动时从 data 目录自动生成。源文件哈希未变化时不会重复导入。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /api/health | 健康检查 |
| GET | /api/meta | 日期范围、门店和商品 |
| GET | /api/dashboard | 汇总、每日趋势、商品与门店排行 |
| GET | /api/data-quality | 清洗覆盖率和问题分布 |
| POST | /api/chat | 可信 AI 数据问答 |

看板示例：

~~~text
GET /api/dashboard?start_date=2026-06-01&end_date=2026-06-30&store_id=S02
~~~

## 验证

~~~powershell
# 后端数据、分析与 AI 一致性测试
Set-Location backend
..\.venv\Scripts\python.exe -m pytest

# 前端类型检查与生产构建
Set-Location ..\frontend
npm run typecheck
npm run build
~~~

测试覆盖：

- 导入结果和清洗基线
- CSV 未变化时幂等导入
- 每日营业额、订单数回勾总计
- Top 10 排序
- 三个指定 AI 问题的数据库数字
- 对话追问
- 未知问题不编造

## 项目结构

~~~text
backend/app/
  ai/             # 模型规划器、工具注册和确定性答案
  api/routes/     # Dashboard、Data Quality、Chat API
  db/             # SQLite、ORM 与初始化
  repositories/   # 唯一分析查询层
  services/       # 数据导入与问答编排
frontend/src/     # React 看板、图表、对话和证据卡
data/             # 原始 POS CSV
~~~

更多交付说明见 [AI_USAGE.md](AI_USAGE.md)、[DEMO.md](DEMO.md) 和 [ASSIGNMENT.md](ASSIGNMENT.md)。

import { Activity, ArrowRight } from "lucide-react";

function App() {
  return (
    <main className="welcome-shell">
      <section className="welcome-card">
        <div className="brand-mark">
          <Activity size={22} strokeWidth={2.4} />
        </div>
        <p className="eyebrow">MONEKI OPERATIONS</p>
        <h1>经营脉搏，清晰可见。</h1>
        <p className="welcome-copy">
          FastAPI 与 React 已连接。下一步将导入真实销售数据并构建可信分析看板。
        </p>
        <a className="docs-link" href="http://127.0.0.1:8000/docs">
          查看 API 文档 <ArrowRight size={17} />
        </a>
      </section>
    </main>
  );
}

export default App;

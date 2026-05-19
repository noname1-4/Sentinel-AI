import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const DEFAULT_STATE = {
  stats: null,
  config: null,
  articles: [],
  loading: true,
  error: "",
};

function App() {
  const [state, setState] = useState(DEFAULT_STATE);

  async function loadDashboard() {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const [statsResponse, configResponse, articlesResponse] = await Promise.all([
        fetch("/api/stats"),
        fetch("/api/config"),
        fetch("/api/articles?limit=25"),
      ]);

      if (!statsResponse.ok || !configResponse.ok || !articlesResponse.ok) {
        throw new Error("API returned an unexpected response.");
      }

      const [stats, config, articles] = await Promise.all([
        statsResponse.json(),
        configResponse.json(),
        articlesResponse.json(),
      ]);

      setState({
        stats,
        config,
        articles: articles.items ?? [],
        loading: false,
        error: "",
      });
    } catch (error) {
      setState((current) => ({
        ...current,
        loading: false,
        error: error instanceof Error ? error.message : "Unable to load dashboard data.",
      }));
    }
  }

  useEffect(() => {
    loadDashboard();
    const timer = window.setInterval(loadDashboard, 30000);
    return () => window.clearInterval(timer);
  }, []);

  const activeSources = useMemo(() => {
    return state.config?.sources?.filter((source) => source.enabled).length ?? 0;
  }, [state.config]);
  const featuredArticles = state.articles.slice(0, 3);
  const leadArticle = featuredArticles[0];

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Sentinel-AI V2</p>
          <h1>Operations Console</h1>
        </div>
        <button className="refresh-button" onClick={loadDashboard} disabled={state.loading}>
          {state.loading ? "Refreshing" : "Refresh"}
        </button>
      </header>

      {state.error ? <div className="error-banner">{state.error}</div> : null}

      <section className="news-band" aria-label="What's News">
        <div className="news-band-header">
          <div>
            <p className="eyebrow">What's News</p>
            <h2>{leadArticle?.title ?? "Waiting for the first processed article"}</h2>
          </div>
          <span>{formatDate(leadArticle?.processed_at)}</span>
        </div>

        <div className="news-band-body">
          <div className="lead-news">
            <span className={`status-pill ${statusClass(leadArticle?.status)}`}>
              {leadArticle?.status ?? "idle"}
            </span>
            <p>{leadArticle?.source_name ?? "Sentinel bot has not written to SQLite yet."}</p>
          </div>

          <div className="news-stack">
            {featuredArticles.slice(1).map((article) => (
              <a
                className="news-link"
                href={article.original_url}
                key={article.normalized_url}
                rel="noreferrer"
                target="_blank"
              >
                <strong>{article.title}</strong>
                <span>{article.source_name}</span>
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="status-grid" aria-label="Runtime status">
        <Metric label="Processed" value={state.stats?.total ?? 0} tone="green" />
        <Metric label="Sent" value={state.stats?.sent ?? 0} tone="blue" />
        <Metric label="Failed" value={state.stats?.failed ?? 0} tone="red" />
        <Metric label="Sources" value={activeSources} tone="amber" />
      </section>

      <section className="runtime-panel">
        <div>
          <span>LLM</span>
          <strong>{state.config?.active_llm ?? "unknown"}</strong>
        </div>
        <div>
          <span>Channels</span>
          <strong>{state.config?.active_channels?.join(", ") || "none"}</strong>
        </div>
        <div>
          <span>Interval</span>
          <strong>{state.config?.poll_interval_seconds ?? 0}s</strong>
        </div>
        <div>
          <span>Last processed</span>
          <strong>{formatDate(state.stats?.last_processed_at)}</strong>
        </div>
      </section>

      <section className="articles-section">
        <div className="section-heading">
          <h2>Recent Articles</h2>
          <span>{state.articles.length} shown</span>
        </div>

        <div className="article-list">
          {state.articles.length === 0 ? (
            <div className="empty-state">No processed articles yet.</div>
          ) : (
            state.articles.map((article) => (
              <article className="article-row" key={article.normalized_url}>
                <div>
                  <h3>{article.title}</h3>
                  <p>{article.source_name}</p>
                </div>
                <div className="article-meta">
                  <span className={`status-pill ${statusClass(article.status)}`}>{article.status}</span>
                  <time>{formatDate(article.processed_at)}</time>
                </div>
              </article>
            ))
          )}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value, tone }) {
  return (
    <div className={`metric metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatDate(value) {
  if (!value) {
    return "never";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function statusClass(status) {
  if (status === "sent") {
    return "status-sent";
  }
  if (status === "failed" || status === "notification_failed") {
    return "status-failed";
  }
  return "status-neutral";
}

createRoot(document.getElementById("root")).render(<App />);

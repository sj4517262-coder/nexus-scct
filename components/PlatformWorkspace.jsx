"use client";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  Database,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingUp,
  FileText,
  Check,
  AlertTriangle,
  Loader2,
  ArrowRight,
} from "lucide-react";
import {
  LineChart,
  Line,
  CartesianGrid,
  Tooltip,
  XAxis,
  YAxis,
  ResponsiveContainer,
} from "recharts";

async function request(path, body) {
  const response = await fetch(`/api/v1/platform${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    ...(body !== undefined
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : JSON.stringify(result.detail),
    );
  return result;
}
const number = (v) =>
  Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
function Card({ title, children }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
      </div>
      <div className="padded">{children}</div>
    </section>
  );
}
function Status({ value }) {
  return (
    <span className={`badge badge-${String(value).toLowerCase()}`}>
      {value}
    </span>
  );
}
const tabs = [
  ["data", "Data foundation", Database],
  ["forecast", "Forecast lab", TrendingUp],
  ["simulation", "Live simulation", Play],
  ["procurement", "Purchase orders", FileText],
  ["agents", "Agent runs", Activity],
  ["knowledge", "Knowledge & policies", ShieldCheck],
  ["monitoring", "Monitoring", Activity],
];

export default function PlatformWorkspace({
  initialTab = "data",
  onChanged = () => {},
}) {
  const [tab, setTab] = useState(initialTab),
    [data, setData] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const [forecasts, setForecasts] = useState([]),
    [storeId, setStoreId] = useState(""),
    [records, setRecords] = useState(null),
    [query, setQuery] = useState(
      "What approvals are required for procurement?",
    ),
    [answer, setAnswer] = useState(null),
    [documentName, setDocumentName] = useState(""),
    [documentText, setDocumentText] = useState(""),
    [deadLetters, setDeadLetters] = useState([]);
  const refresh = useCallback(async () => {
    try {
      setData(await request("/status"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    refresh();
    const timer = setInterval(() => {
      if (!document.hidden) refresh();
    }, 10000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (tab === "forecast")
      request("/forecasts")
        .then((r) => {
          setForecasts(r.points);
          setStoreId((s) => s || r.points[0]?.store_id || "");
        })
        .catch((e) => setError(e.message));
    if (tab === "monitoring")
      request("/dead-letters")
        .then(setDeadLetters)
        .catch((e) => setError(e.message));
  }, [tab]);
  async function run(path, body, success) {
    setBusy(true);
    setError("");
    try {
      const r = await request(path, body);
      setMessage(success || "Operation completed.");
      await refresh();
      onChanged();
      return r;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  if (!data)
    return (
      <div className="panel padded">
        {error ? (
          <p role="alert">{error}</p>
        ) : (
          <p>
            <Loader2 className="spin" size={17} /> Loading platform services…
          </p>
        )}
        <button className="button secondary" onClick={refresh}>
          Retry
        </button>
      </div>
    );
  const model = data.models.demand,
    risk = data.models.risk;
  return (
    <div className="platform-workspace">
      <div className="platform-tabs" role="tablist" aria-label="Platform tools">
        {tabs.map(([id, label, Icon]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            className={tab === id ? "selected" : ""}
            onClick={() => {
              setTab(id);
              setRecords(null);
            }}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="notice" role="status">
          <Check size={17} />
          {message}
          <button className="text-button" onClick={() => setMessage("")}>
            Dismiss
          </button>
        </div>
      )}
      {tab === "data" && (
        <>
          <div className="notice">
            <Database size={19} />
            <span>
              Historical sources remain separate. Simulation links are
              explicitly labelled statistical projections, not claims that these
              organizations share products or suppliers.
            </span>
          </div>
          <div className="agent-grid">
            {data.sources.map((s) => (
              <Card key={s.source_id} title={s.name}>
                <div className="source-id">{s.source_id}</div>
                <p>{s.manifest.grain || s.manifest.forecast_grain}</p>
                <p className="helper">{s.license}</p>
                <p className="helper">
                  {s.manifest.rows
                    ? `${number(s.manifest.rows)} records`
                    : `${number(s.manifest.products)} products · ${s.manifest.stores} stores · ${number(s.manifest.series)} series`}
                </p>
                <a href={s.url} target="_blank" rel="noreferrer">
                  Source documentation ↗
                </a>
                <div className="row-actions" style={{ marginTop: 15 }}>
                  <button
                    className="button secondary"
                    onClick={async () => {
                      try {
                        setRecords({
                          source: s.source_id,
                          rows: await request(`/source-records/${s.source_id}`),
                        });
                      } catch (e) {
                        setError(e.message);
                      }
                    }}
                  >
                    Inspect records
                  </button>
                </div>
              </Card>
            ))}
          </div>
          {!data.sources.length && (
            <Card title="No sources imported">
              <p>
                Run the documented bootstrap command to ingest M5 and public
                datasets.
              </p>
            </Card>
          )}
          {data.m5_validation && (
            <Card title="M5 integrity report">
              <div className="validation-grid">
                {Object.entries(data.m5_validation.checks).map(
                  ([key, passed]) => (
                    <div key={key}>
                      {passed ? (
                        <Check size={15} className="text-green" />
                      ) : (
                        <AlertTriangle size={15} className="text-amber" />
                      )}
                      {key.replace(/_/g, " ")}
                    </div>
                  ),
                )}
              </div>
              <p className="helper">
                {number(data.m5_validation.persisted_demand_rows)}{" "}
                product/store/day records ·{" "}
                {data.m5_validation.imported_product_days} imported days. Full
                store-level history: {data.m5_validation.raw_days} days.
              </p>
            </Card>
          )}
          {records && (
            <Card title={`Source records · ${records.source}`}>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      {Object.keys(records.rows[0] || {}).map((k) => (
                        <th key={k}>{k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {records.rows.map((row, i) => (
                      <tr key={i}>
                        {Object.values(row).map((v, j) => (
                          <td key={j}>{String(v)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
      {tab === "forecast" && (
        <>
          {model ? (
            <>
              <div className="notice">
                <TrendingUp size={18} />
                <span>
                  M5 store-level forecasting. Train through {model.train_end};
                  validation {model.validation_start}–{model.validation_end};
                  untouched test {model.test_start}–{model.test_end}. Selection
                  uses validation WAPE.
                </span>
              </div>
              <div className="stats-grid three">
                <div className="stat">
                  <span>Selected model</span>
                  <strong style={{ fontSize: 20 }}>
                    {model.selected_model.replace(/_/g, " ")}
                  </strong>
                  <p>Winner of the validation comparison</p>
                </div>
                <div className="stat">
                  <span>Candidate test WAPE</span>
                  <strong>{number(model.test.candidate.wape)}%</strong>
                  <p>Recursive 28-day forecast</p>
                </div>
                <div className="stat">
                  <span>Seasonal baseline test WAPE</span>
                  <strong>{number(model.test.baseline.wape)}%</strong>
                  <p>Same dates and forecast horizon</p>
                </div>
              </div>
              <Card title="Model comparison">
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Partition / model</th>
                        <th>WAPE %</th>
                        <th>MAE units</th>
                        <th>RMSE units</th>
                      </tr>
                    </thead>
                    <tbody>
                      {["validation", "test"].flatMap((split) =>
                        ["candidate", "baseline"].map((name) => (
                          <tr key={split + name}>
                            <td>
                              {split} / {name}
                            </td>
                            <td>{number(model[split][name].wape)}</td>
                            <td>{number(model[split][name].mae)}</td>
                            <td>{number(model[split][name].rmse)}</td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="helper">
                  MLflow run: {model.run_id}. Forecasts use only historical
                  observations and recursively predicted values; no future
                  demand is supplied to lag features.
                </p>
              </Card>
              <Card title="Store forecast">
                <select
                  aria-label="M5 store"
                  value={storeId}
                  onChange={(e) => setStoreId(e.target.value)}
                >
                  {[...new Set(forecasts.map((f) => f.store_id))].map((id) => (
                    <option key={id}>{id}</option>
                  ))}
                </select>
                <div className="chart">
                  <ResponsiveContainer width="100%" height={290}>
                    <LineChart
                      data={forecasts.filter((f) => f.store_id === storeId)}
                    >
                      <CartesianGrid stroke="#263c50" />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: "#aac0d4", fontSize: 10 }}
                        minTickGap={40}
                      />
                      <YAxis tick={{ fill: "#aac0d4", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{
                          background: "#142a3c",
                          border: "1px solid #304858",
                        }}
                      />
                      <Line dataKey="forecast" stroke="#73e1c4" dot={false} isAnimationActive={false} />
                      <Line
                        dataKey="lower"
                        isAnimationActive={false}
                        stroke="#6484a1"
                        strokeDasharray="4 4"
                        dot={false}
                      />
                      <Line
                        dataKey="upper"
                        isAnimationActive={false}
                        stroke="#6484a1"
                        strokeDasharray="4 4"
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="helper">
                  Historical as-of {model.as_of}. Dates represent the original
                  M5 timeline. The simulator projects patterns forward
                  explicitly; it does not relabel historical forecasts as
                  current observations.
                </p>
              </Card>
            </>
          ) : (
            <Card title="Model not trained">
              <p>Run the training pipeline after data ingestion.</p>
            </Card>
          )}
          {risk && (
            <Card title="Delivery delay risk model">
              <div className="validation-grid">
                <span>ROC AUC: {number(risk.metrics.roc_auc)}</span>
                <span>Brier score: {number(risk.metrics.brier)}</span>
                <span>
                  Baseline Brier: {number(risk.metrics.baseline_brier)}
                </span>
                <span>Test orders: {number(risk.test_rows)}</span>
              </div>
              <p className="helper">
                DataCo order-level chronological test {risk.test_start}–
                {risk.test_end}. Actual delivery outcomes, shipping dates and
                delivery status are excluded from features. This predicts delay
                risk, not supplier financial failure.
              </p>
            </Card>
          )}
        </>
      )}
      {tab === "simulation" && (
        <>
          <div className="notice">
            <Play size={18} />
            <span>
              The simulator applies M5 demand and DataCo logistics patterns to
              synthetic entities. Approved actions execute in the built-in
              simulation ERP; no real purchases or carrier messages are sent.
            </span>
          </div>
          <div className="stats-grid three">
            <div className="stat">
              <span>State database</span>
              <strong>{data.storage}</strong>
              <p>Atomic state changes and event outbox</p>
            </div>
            <div className="stat">
              <span>Event worker</span>
              <strong style={{ fontSize: 23 }}>{data.worker.status}</strong>
              <p>Kafka consumer and outbox publisher</p>
            </div>
            <div className="stat">
              <span>Simulation tick</span>
              <strong>{data.scenario?.tick || 0}</strong>
              <p>Historical-pattern future scenario</p>
            </div>
          </div>
          <Card title="Run the supply chain">
            <p>
              Each tick publishes one demand event per simulation warehouse.
              Stock changes, delay patterns, replenishment planning, and
              receipts are processed through Kafka.
            </p>
            <div className="row-actions" style={{ marginTop: 20 }}>
              <button
                className="button"
                disabled={busy}
                onClick={() =>
                  run(
                    "/simulate",
                    { ticks: 1, seed: 42 },
                    "Simulation events queued. The Kafka worker will update state and generate plans.",
                  )
                }
              >
                <Play size={16} />
                Run 1 day
              </button>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() =>
                  run(
                    "/simulate",
                    { ticks: 7, seed: 42 },
                    "Seven simulation days queued.",
                  )
                }
              >
                Run 7 days
              </button>
              <button className="button secondary" onClick={refresh}>
                <RefreshCw size={16} />
                Refresh status
              </button>
            </div>
            <p className="helper" style={{ marginTop: 15 }}>
              Review generated plans in Decision center. Approval publishes an
              execution event; the worker creates orders and replans with
              inbound commitments.
            </p>
          </Card>
          <Card title="Pipeline activity">
            <div className="validation-grid">
              {Object.entries(data.counts).map(([key, value]) => (
                <div key={key}>
                  <Activity size={15} />
                  {key.replace(/_/g, " ")}: <strong>{number(value)}</strong>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
      {tab === "procurement" && (
        <Card title="Executed simulation purchase orders">
          <p className="helper">
            These orders are created by the approved execution loop. Public San
            Francisco procurement remains in the separate source browser.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Order</th>
                  <th>Supplier</th>
                  <th>Destination</th>
                  <th>Units</th>
                  <th>USD</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.purchase_orders.map((p) => (
                  <tr key={p.id}>
                    <td>{p.id}</td>
                    <td>{p.supplier_id}</td>
                    <td>{p.warehouse_id}</td>
                    <td>{number(p.quantity)}</td>
                    <td>{number(p.value_usd)}</td>
                    <td>
                      <Status value={p.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data.purchase_orders.length && (
              <div className="empty">
                No executed orders yet. Run a simulation and approve a
                procurement plan.
              </div>
            )}
          </div>
        </Card>
      )}
      {tab === "agents" && (
        <>
          <div className="notice">
            <Activity size={18} />
            <span>
              LangGraph connects trained demand and delay-risk models, document
              retrieval, OR-Tools sourcing, structured approval policy, and
              execution-ready plans.
            </span>
          </div>
          {data.planning_runs
            .slice()
            .reverse()
            .map((run) => (
              <Card key={run.id} title={`${run.engine} · ${run.warehouse_id}`}>
                <div className="row-actions">
                  <Status value={run.status} />
                  <small>
                    {run.duration_ms} ms ·{" "}
                    {new Date(run.created_at).toLocaleString()}
                  </small>
                </div>
                <div className="agent-reports">
                  {Object.entries(run.reports || {}).map(([name, text]) => (
                    <div key={name}>
                      <strong>{name}</strong>
                      <p>{text}</p>
                    </div>
                  ))}
                </div>
                <details>
                  <summary>Model provenance and policy citations</summary>
                  <pre className="json-detail">
                    {JSON.stringify(
                      { model: run.model_provenance, citations: run.citations },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </Card>
            ))}
          {!data.planning_runs.length && (
            <Card title="No planning runs yet">
              <p>Run a simulation to generate model-grounded plans.</p>
            </Card>
          )}
        </>
      )}
      {tab === "knowledge" && (
        <>
          <Card title="Policy and supplier document retrieval">
            <form
              className="chat-input"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  setAnswer(
                    await request(`/rag?q=${encodeURIComponent(query)}`),
                  );
                } catch (err) {
                  setError(err.message);
                }
              }}
            >
              <input
                aria-label="Policy question"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                minLength={3}
                maxLength={2000}
              />
              <button className="button">
                <Search size={16} />
                Retrieve
              </button>
            </form>
            {answer && (
              <>
                <p className="helper">{answer.generation}</p>
                {answer.citations.map((c, i) => (
                  <div className="knowledge-passage" key={i}>
                    <strong>
                      {c.source} · §{c.chunk}
                    </strong>
                    <p>{c.text}</p>
                    <small>
                      Relevance {c.score} · SHA-256 {c.sha256.slice(0, 16)}…
                    </small>
                  </div>
                ))}
              </>
            )}
          </Card>
          <div className="two-columns">
            <Card title="Add a supplier or policy document">
              <form
                className="record-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const r = await run(
                    "/documents",
                    { name: documentName, text: documentText },
                    "Knowledge document indexed for retrieval.",
                  );
                  if (r) {
                    setDocumentName("");
                    setDocumentText("");
                  }
                }}
              >
                <label>
                  Document title
                  <input
                    required
                    minLength={3}
                    maxLength={120}
                    value={documentName}
                    onChange={(e) => setDocumentName(e.target.value)}
                  />
                </label>
                <label>
                  Document text
                  <textarea
                    required
                    minLength={40}
                    maxLength={20000}
                    rows={6}
                    value={documentText}
                    onChange={(e) => setDocumentText(e.target.value)}
                  />
                </label>
                <button className="button" disabled={busy}>
                  Save document
                </button>
              </form>
            </Card>
            <Card title="Authoritative execution policy">
              <pre className="json-detail">
                {JSON.stringify(data.policy, null, 2)}
              </pre>
              <p className="helper">
                Uploaded text is retrieval context only. It cannot override this
                structured policy or grant execution permissions.
              </p>
            </Card>
          </div>
        </>
      )}
      {tab === "monitoring" && (
        <>
          <div className="stats-grid three">
            <div className="stat">
              <span>Worker health</span>
              <strong style={{ fontSize: 21 }}>{data.worker.status}</strong>
              <p>Heartbeat age: {data.worker.age_seconds ?? "—"} seconds</p>
            </div>
            <div className="stat">
              <span>Pending delivery</span>
              <strong>{data.counts.outbox_pending}</strong>
              <p>Unacknowledged events remain retryable</p>
            </div>
            <div className="stat">
              <span>Dead-letter events</span>
              <strong>{data.counts.dead_letters}</strong>
              <p>Failures preserved for investigation</p>
            </div>
          </div>
          <Card title="API and model monitoring">
            <div className="validation-grid">
              <span>Requests: {number(data.monitoring.requests)}</span>
              <span>Server errors: {data.monitoring.server_errors}</span>
              <span>
                Cumulative request seconds: {data.monitoring.request_seconds}
              </span>
            </div>
            <p className="helper">{data.monitoring.model_drift}</p>
            <p className="helper">Demand drift: {data.drift?.status || "Awaiting simulation"} · rolling WAPE: {data.drift?.wape == null ? "—" : `${data.drift.wape.toFixed(2)}%`} · {data.drift?.window?.length || 0} observations</p>
            <p className="helper">
              Prometheus metrics: API /metrics · MLflow: http://localhost:5001
            </p>
          </Card>
          <Card title="Failure recovery">
            {deadLetters.map((e) => (
              <div className="knowledge-passage" key={e.id}>
                <strong>{e.id}</strong>
                <p>{e.error}</p>
                <small>{e.created_at}</small>
                <button
                  className="button secondary"
                  disabled={busy}
                  onClick={() =>
                    run(
                      `/dead-letters/${encodeURIComponent(e.id)}/retry`,
                      {},
                      "Replay queued; inspect subsequent worker results.",
                    )
                  }
                >
                  Retry event
                </button>
              </div>
            ))}
            {!deadLetters.length && (
              <div className="empty">
                <Check size={25} />
                No dead letters.
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

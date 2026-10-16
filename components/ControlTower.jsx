"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PlatformWorkspace from "./PlatformWorkspace";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  Check,
  ChevronRight,
  HelpCircle as CircleHelp,
  ClipboardCheck,
  Cpu,
  Globe2,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  Network,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Truck,
  X,
  Zap,
  AlertTriangle,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const NAV = [
  ["overview", "Command center", LayoutDashboard],
  ["platform", "Platform lab", Zap],
  ["shipments", "Shipments", Truck],
  ["inventory", "Inventory", Boxes],
  ["suppliers", "Supplier risk", ShieldCheck],
  ["disruptions", "Disruptions", AlertTriangle],
  ["decisions", "Decision center", ClipboardCheck],
  ["agents", "Analysis agents", Cpu],
  ["twin", "Digital twin", Network],
  ["forecast", "Demand forecast", TrendingUp],
  ["events", "Event stream", Activity],
  ["copilot", "ARIA copilot", Sparkles],
];
const DESCRIPTIONS = {
  platform:
    "Verified data, trained models, live simulation, procurement, and monitoring.",
  overview:
    "Your supply network, in focus. See what needs attention and keep operations moving.",
  shipments:
    "Track inbound freight, update routes, and record warehouse receipts.",
  inventory: "Balance stock across your network with capacity-aware transfers.",
  suppliers:
    "Manage suppliers and their assessed risk. Higher scores mean greater risk.",
  disruptions:
    "Capture exceptions, analyze exposure, and track their resolution.",
  decisions:
    "Review proposed response plans with a complete record of your reasoning.",
  agents:
    "LangGraph orchestration with trained models, retrieved policies, and OR-Tools optimization.",
  twin: "Explore supplier-to-warehouse connections from recorded shipments.",
  forecast:
    "Chronological M5 forecasting, baseline comparison, and MLflow experiment results.",
  events:
    "A durable activity history of workspace changes, decisions, and operational events.",
  copilot:
    "Ask about your operations. ARIA answers from the latest saved workspace records.",
};
const n = (x) => Number(x || 0).toLocaleString();
const usd = (x) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(x || 0);
const dt = (x) =>
  x
    ? new Date(x).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
const today = () => new Date().toLocaleDateString("en-CA");
const tip = {
  background: "#132337",
  border: "1px solid #304258",
  borderRadius: 8,
  color: "#e5edf6",
};

async function api(path, body, method = "POST") {
  const response = await fetch(`/api/v1${path}`, {
    credentials: "same-origin",
    cache: "no-store",
    ...(body !== undefined
      ? {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {}),
    signal: AbortSignal.timeout(15000),
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      "The service is unavailable. Start the API server and try again.",
    );
  }
  if (!response.ok) {
    const error = new Error(
      Array.isArray(result.detail)
        ? result.detail
            .map((x) => `${x.loc.slice(1).join(".")}: ${x.msg}`)
            .join("; ")
        : result.detail || "Request failed",
    );
    error.status = response.status;
    throw error;
  }
  return result;
}

function Badge({ value }) {
  return (
    <span
      className={`badge badge-${String(value).toLowerCase().replace(/_/g, "-")}`}
    >
      {String(value).replace(/_/g, " ")}
    </span>
  );
}
function Empty({ children = "No records to show." }) {
  return (
    <div className="empty">
      <Check size={24} />
      <p>{children}</p>
    </div>
  );
}
function Panel({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Stat({ label, value, detail, icon: Icon = Activity, tone = "blue" }) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <Icon size={18} className={`text-${tone}`} />
      </div>
      <strong>{value}</strong>
      <p>{detail}</p>
    </div>
  );
}
function Table({ columns, rows, rowKey = "id", empty }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.label}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row[rowKey] || i}>
              {columns.map((c) => (
                <td key={c.label}>{c.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && (
        <Empty>
          {empty ||
            "No matching records. Try a different search or add a record."}
        </Empty>
      )}
    </div>
  );
}

function Modal({ title, subtitle, children, close, busy }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.querySelector("input,select,textarea,button")?.focus();
    function key(event) {
      if (event.key === "Escape" && !busy) close();
      if (event.key === "Tab") {
        const fields = [
          ...ref.current.querySelectorAll(
            'button:not([disabled]),input,select,textarea,[tabindex="0"]',
          ),
        ];
        const first = fields[0],
          last = fields[fields.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [close, busy]);
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) close();
      }}
    >
      <section
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="panel-heading">
          <div>
            <h2 id="modal-title">{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={close}
            disabled={busy}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function RecordForm({ config, close, onSaved }) {
  const [values, setValues] = useState(config.values || {});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = config.transform ? config.transform(values) : values;
      await api(config.path, body, config.method || "POST");
      onSaved(config.success || "Changes saved.");
      close();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={config.title}
      subtitle={config.subtitle}
      close={close}
      busy={busy}
    >
      <form onSubmit={submit} className="record-form">
        {config.fields.map((field) => (
          <label key={field.key}>
            {field.label}
            {field.type === "select" ? (
              <select
                value={values[field.key] ?? ""}
                required={field.required !== false}
                onChange={(e) =>
                  setValues({ ...values, [field.key]: e.target.value })
                }
              >
                <option value="">Select…</option>
                {field.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            ) : field.type === "textarea" ? (
              <textarea
                required={field.required !== false}
                minLength={field.minLength || 1}
                maxLength={field.maxLength || 2000}
                rows={3}
                value={values[field.key] ?? ""}
                onChange={(e) =>
                  setValues({ ...values, [field.key]: e.target.value })
                }
              />
            ) : (
              <input
                type={field.type || "text"}
                required={field.required !== false}
                min={field.min}
                max={field.max}
                minLength={field.minLength}
                maxLength={field.maxLength || 200}
                step={field.step || (field.type === "number" ? "1" : undefined)}
                value={values[field.key] ?? ""}
                onChange={(e) =>
                  setValues({
                    ...values,
                    [field.key]:
                      field.type === "number" && e.target.value !== ""
                        ? Number(e.target.value)
                        : e.target.value,
                  })
                }
              />
            )}
            {field.hint && <small>{field.hint}</small>}
          </label>
        ))}
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        <div className="form-actions">
          <button
            type="button"
            className="button secondary"
            onClick={close}
            disabled={busy}
          >
            Cancel
          </button>
          <button className="button" disabled={busy}>
            {busy ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <Check size={16} />
            )}
            {config.submit || "Save changes"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Auth({ onReady }) {
  const [setup, setSetup] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState("");
  const check = useCallback(() => {
    setError("");
    api("/auth/status")
      .then((x) => setSetup(x.setup_required))
      .catch((e) => setError(e.message));
  }, []);
  useEffect(check, [check]);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onReady(
        await api(setup ? "/auth/setup" : "/auth/login", { email, password }),
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <div className="auth-intro">
        <div className="brand">
          <div className="brand-mark">
            <Network />
          </div>
          <span>
            NEXUS<span className="brand-sub">SUPPLY CHAIN INTELLIGENCE</span>
          </span>
        </div>
        <span className="eyebrow">A CLEARER VIEW OF YOUR OPERATIONS</span>
        <h1>
          Every connection.
          <br />
          <em>One control tower.</em>
        </h1>
        <p>
          Bring your supply network together. Spot disruptions, balance
          inventory, and make informed decisions with a complete operational
          record.
        </p>
        <div className="auth-features">
          <span>
            <ShieldCheck size={18} /> Account-protected workspace
          </span>
          <span>
            <Activity size={18} /> Persistent activity history
          </span>
          <span>
            <Globe2 size={18} /> Connected supply network
          </span>
        </div>
        <div className="auth-note">LOCAL WORKSPACE · SAMPLE DATA INCLUDED</div>
      </div>
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-icon">
          <ArrowUpRight size={25} />
        </div>
        <h2>{setup ? "Create your workspace" : "Welcome back"}</h2>
        <p>
          {setup
            ? "Set up the workspace owner account to get started. Your operations are saved on this computer."
            : "Sign in to your NEXUS control tower."}
        </p>
        {setup !== null && (
          <>
            <label>
              Email address
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                required
                minLength={10}
                maxLength={128}
                autoComplete={setup ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 10 characters"
              />
            </label>
            <button className="button" disabled={busy}>
              {busy ? (
                <Loader2 size={18} className="spin" />
              ) : (
                <ArrowRight size={18} />
              )}
              {setup ? "Create workspace" : "Sign in"}
            </button>
          </>
        )}
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {setup === null && (
          <button type="button" className="button secondary" onClick={check}>
            <RefreshCw size={16} />
            Retry connection
          </button>
        )}
        <div className="auth-foot">
          <CircleHelp size={16} /> The first account owns this local workspace.
        </div>
      </form>
    </main>
  );
}

function NetworkMap({ data, detailed = false }) {
  const [selected, setSelected] = useState(null);
  const all = [
    ...data.suppliers.map((s) => ({
      ...s,
      type: "Supplier",
      tone: s.risk_score >= 50 ? "#f6b66a" : "#69a9ff",
    })),
    ...data.warehouses.map((w) => ({
      ...w,
      type: "Warehouse",
      tone: "#57dfbd",
    })),
  ];
  const positions = Object.fromEntries(
    all.map((item) => [
      item.id,
      { x: (item.lng + 180) * 2.4 + 18, y: (80 - item.lat) * 2.3 + 16 },
    ]),
  );
  const edges = data.shipments.filter((s) => s.status !== "DELIVERED");
  return (
    <div className="map-wrap">
      <svg
        role="img"
        aria-label="Supply network schematic showing suppliers, warehouses and active shipment links"
        viewBox="0 0 900 390"
        className="network-map"
      >
        <defs>
          <pattern
            id="map-grid"
            width="45"
            height="39"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M45 0H0V39"
              fill="none"
              stroke="#1c3044"
              strokeWidth=".7"
            />
          </pattern>
          <radialGradient id="map-glow">
            <stop stopColor="#18394c" />
            <stop offset="1" stopColor="#0c1928" />
          </radialGradient>
        </defs>
        <rect width="900" height="390" fill="url(#map-glow)" />
        <rect width="900" height="390" fill="url(#map-grid)" />
        <g fill="#1c3545" stroke="#284558" strokeWidth="1.2" opacity=".85">
          <path d="M88 71L153 43 231 57 268 90 236 120 212 145 181 147 172 185 143 161 127 121 103 115Z" />
          <path d="M194 182L228 195 266 231 252 275 228 320 214 292 208 250 184 219Z" />
          <path d="M407 70L455 48 498 67 486 102 444 113 426 94Z" />
          <path d="M430 117L478 116 519 151 513 199 479 244 458 217 448 185 421 158Z" />
          <path d="M489 59L595 39 703 48 784 84 768 112 710 119 682 154 635 148 610 197 588 171 561 133 520 128 493 97Z" />
          <path d="M689 211L711 205 740 223 719 235Z" />
          <path d="M711 261L764 248 808 281 788 307 742 305 709 283Z" />
        </g>
        {edges.map((s) => {
          const a = positions[s.supplier_id],
            b = positions[s.warehouse_id];
          if (!a || !b) return null;
          return (
            <path
              key={s.id}
              d={`M${a.x},${a.y} Q${(a.x + b.x) / 2},${Math.min(a.y, b.y) - 50} ${b.x},${b.y}`}
              stroke={s.status === "DELAYED" ? "#e4ac62" : "#4ba5b8"}
              fill="none"
              opacity=".4"
              strokeWidth="1.4"
              strokeDasharray={s.status === "DELAYED" ? "4 5" : undefined}
            />
          );
        })}
        {all.map((item) => {
          const p = positions[item.id];
          return (
            <g
              key={item.id}
              role="button"
              tabIndex={0}
              aria-label={`${item.type}: ${item.name}`}
              onClick={() => setSelected(item)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setSelected(item);
                }
              }}
              style={{ cursor: "pointer" }}
            >
              <circle cx={p.x} cy={p.y} r={14} fill={item.tone} opacity=".08" />
              <circle
                cx={p.x}
                cy={p.y}
                r={4.5}
                fill={item.tone}
                stroke="#0c1928"
                strokeWidth={2}
              />
              {detailed && (
                <text x={p.x + 8} y={p.y - 8} fontSize="9" fill="#acc3d5">
                  {item.name.split(" ")[0]}
                </text>
              )}
              <title>{item.name}</title>
            </g>
          );
        })}
        <text x="30" y="365" fill="#5b7a94" fontSize="10" letterSpacing="2">
          SCHEMATIC · ENTITY LOCATIONS, NOT LIVE GPS
        </text>
      </svg>
      <div className="map-legend">
        <span>
          <i className="dot blue" />
          Suppliers
        </span>
        <span>
          <i className="dot green" />
          Warehouses
        </span>
        <span>
          <i className="dot amber" />
          Elevated risk
        </span>
        <span>{edges.length} active routes</span>
      </div>
      {selected && (
        <div className="map-detail">
          <div>
            <small>
              {selected.type} · {selected.id}
            </small>
            <strong>{selected.name}</strong>
            <span>
              {selected.type === "Supplier"
                ? `Risk ${selected.risk_score}/100 · ${selected.country}`
                : `${n(selected.stock)} units · ${selected.utilization}% utilized`}
            </span>
          </div>
          <button
            className="icon-button"
            onClick={() => setSelected(null)}
            aria-label="Close location details"
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}

function ForecastChart({ forecast: fc }) {
  const points = [
    ...fc.history.map((p) => ({ date: p.date.slice(5), actual: p.quantity })),
    ...fc.points.map((p) => ({
      date: p.date.slice(5),
      forecast: p.forecast,
      range: [p.lower, p.upper],
    })),
  ];
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart
          data={points}
          margin={{ top: 15, right: 15, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#203044" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#8198ae", fontSize: 10 }}
            minTickGap={35}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#8198ae", fontSize: 10 }}
            width={48}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip contentStyle={tip} />
          <Area
            dataKey="range"
            name="Prediction range"
            stroke="none"
            fill="#54d9b7"
            fillOpacity={0.12}
          />
          <Area
            dataKey="actual"
            name="Historical demand"
            stroke="#6daaff"
            fill="#6daaff"
            fillOpacity={0.08}
            strokeWidth={2}
          />
          <Area
            dataKey="forecast"
            name="Forecast"
            stroke="#57dfbd"
            fill="transparent"
            strokeWidth={2}
            strokeDasharray="5 4"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function Copilot() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hello, I’m ARIA. I can summarize your saved operations and explain what needs attention. What would you like to explore?",
    },
  ]);
  const [input, setInput] = useState(""),
    [busy, setBusy] = useState(false);
  const end = useRef(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, busy]);
  async function send(text) {
    const message = (text || input).trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: message }]);
    try {
      const answer = await api("/copilot/chat", { message });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: answer.answer,
          source: `${answer.sources.join(" · ")} · ${dt(answer.generated_at)}`,
        },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "error", text: e.message }]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="copilot-layout">
      <Panel
        title="ARIA operational assistant"
        subtitle="Grounded in your workspace · deterministic answers"
        className="chat-panel"
      >
        <div className="chat-messages" aria-live="polite">
          {messages.map((m, i) => (
            <div className={`message message-${m.role}`} key={i}>
              <span className="eyebrow">
                {m.role === "user"
                  ? "YOU"
                  : m.role === "error"
                    ? "CONNECTION ERROR"
                    : "ARIA"}
              </span>
              <p>{m.text}</p>
              {m.source && <small>{m.source}</small>}
            </div>
          ))}
          {busy && (
            <div className="message">
              <Loader2 size={18} className="spin" /> Reading operations…
            </div>
          )}
          <div ref={end} />
        </div>
        <form
          className="chat-input"
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
        >
          <input
            aria-label="Ask ARIA"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={2000}
            placeholder="Ask about suppliers, inventory, or decisions…"
          />
          <button
            className="button"
            disabled={busy || !input.trim()}
            aria-label="Send message"
          >
            <Send size={17} />
          </button>
        </form>
      </Panel>
      <Panel
        title="Start with a question"
        subtitle="Operational context, on demand"
      >
        {[
          "Which suppliers have the highest risk?",
          "What inventory needs attention?",
          "Summarize pending decisions",
          "How is delivery performance?",
          "What is the demand forecast?",
        ].map((q) => (
          <button
            key={q}
            className="suggestion"
            disabled={busy}
            onClick={() => send(q)}
          >
            {q}
            <ArrowUpRight size={16} />
          </button>
        ))}
        <p className="helper padded">
          ARIA is a rule-based assistant. It summarizes recorded data and does
          not execute actions or call an external AI service.
        </p>
      </Panel>
    </div>
  );
}

export default function ControlTower() {
  const [user, setUser] = useState(undefined),
    [data, setData] = useState(null),
    [view, setView] = useState("overview");
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("ALL"),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [modal, setModal] = useState(null),
    [menu, setMenu] = useState(false),
    [refreshing, setRefreshing] = useState(false);
  const demandFile = useRef(null),
    requestRunning = useRef(false);
  useEffect(() => {
    api("/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);
  const refresh = useCallback(async () => {
    if (requestRunning.current) return;
    requestRunning.current = true;
    setRefreshing(true);
    try {
      const result = await api("/snapshot");
      setData(result);
      setError("");
    } catch (e) {
      if (e.status === 401) {
        setUser(null);
        setData(null);
      } else setError(e.message);
    } finally {
      requestRunning.current = false;
      setRefreshing(false);
    }
  }, []);
  useEffect(() => {
    if (!user) return;
    refresh();
    const interval = setInterval(() => {
      if (!document.hidden) refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, [user, refresh]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  const closeModal = useCallback(() => setModal(null), []);
  function navigate(next) {
    setView(next);
    setQuery("");
    setFilter("ALL");
    setMenu(false);
  }
  function saved(message) {
    setToast(message);
    refresh();
  }
  async function action(path, body = {}, method = "POST") {
    try {
      await api(path, body, method);
      saved("Operation saved.");
    } catch (e) {
      setError(e.message);
    }
  }
  if (user === undefined)
    return (
      <div className="loading-screen">
        <Loader2 className="spin" />
        <p>Opening your control tower…</p>
      </div>
    );
  if (!user) return <Auth onReady={setUser} />;
  if (!data)
    return (
      <div className="loading-screen">
        <Network size={36} />
        <h2>Connecting your workspace</h2>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <button className="button" onClick={refresh}>
              Retry connection
            </button>
          </>
        ) : (
          <Loader2 className="spin" />
        )}
      </div>
    );

  const k = data.kpis;
  const supplierName = (id) =>
    data.suppliers.find((s) => s.id === id)?.name || id;
  const warehouseName = (id) =>
    data.warehouses.find((w) => w.id === id)?.name || id;
  const warehouseOptions = data.warehouses.map((w) => ({
    value: w.id,
    label: `${w.name} (${w.utilization}% full)`,
  }));
  const supplierOptions = data.suppliers.map((s) => ({
    value: s.id,
    label: s.name,
  }));
  const matches = (row) =>
    JSON.stringify(row).toLowerCase().includes(query.toLowerCase());
  const selectField = (key, label, options) => ({
    key,
    label,
    type: "select",
    options,
  });
  const warehouseField = (
    key = "warehouse_id",
    label = "Destination warehouse",
  ) => selectField(key, label, warehouseOptions);
  function supplierForm(item) {
    setModal({
      title: item ? "Edit supplier" : "Add supplier",
      path: `/suppliers${item ? `/${item.id}` : ""}`,
      method: item ? "PATCH" : "POST",
      values: item
        ? Object.fromEntries(
            [
              "name",
              "country",
              "category",
              "risk_score",
              "monthly_volume",
              "lat",
              "lng",
            ].map((key) => [key, item[key]]),
          )
        : { risk_score: 25, monthly_volume: 0, lat: 0, lng: 0 },
      fields: [
        { key: "name", label: "Supplier name", minLength: 2 },
        { key: "country", label: "Country", minLength: 2 },
        { key: "category", label: "Category", minLength: 2 },
        {
          key: "risk_score",
          label: "Assessed risk (0–100)",
          type: "number",
          min: 0,
          max: 100,
          hint: "Higher means riskier. This score is supplied by the operator.",
        },
        {
          key: "monthly_volume",
          label: "Monthly volume (units)",
          type: "number",
          min: 0,
        },
        {
          key: "lat",
          label: "Latitude",
          type: "number",
          min: -90,
          max: 90,
          step: "any",
        },
        {
          key: "lng",
          label: "Longitude",
          type: "number",
          min: -180,
          max: 180,
          step: "any",
        },
      ],
    });
  }
  function transferForm(plan) {
    setModal({
      title: "Record inventory transfer",
      subtitle:
        "Updates both warehouse balances atomically. Record only a transfer you intend to reflect in local stock.",
      path: "/inventory/transfer",
      values: plan
        ? {
            from_warehouse: plan.from_warehouse,
            to_warehouse: plan.to_warehouse,
            quantity: plan.quantity,
          }
        : {},
      fields: [
        warehouseField("from_warehouse", "From warehouse"),
        warehouseField("to_warehouse", "To warehouse"),
        { key: "quantity", label: "Quantity (units)", type: "number", min: 1 },
      ],
      submit: "Record transfer",
    });
  }
  function shipmentForm() {
    setModal({
      title: "Create shipment",
      path: "/shipments",
      values: { eta: today(), quantity: 1000, cost_usd: 0 },
      fields: [
        { key: "tracking_number", label: "Tracking number", minLength: 2 },
        selectField("supplier_id", "Supplier", supplierOptions),
        warehouseField(),
        { key: "carrier", label: "Carrier", minLength: 2 },
        { key: "quantity", label: "Quantity (units)", type: "number", min: 1 },
        {
          key: "cost_usd",
          label: "Transport cost (USD)",
          type: "number",
          min: 0,
          step: "0.01",
        },
        { key: "eta", label: "Expected delivery", type: "date" },
      ],
    });
  }
  function rerouteForm(s) {
    setModal({
      title: `Reroute ${s.tracking_number}`,
      subtitle:
        "Records a planned route change. Carrier execution must be arranged separately.",
      path:
        s.source === "simulation"
          ? "/platform/reroute-plan"
          : `/shipments/${s.id}/reroute`,
      transform: (values) =>
        s.source === "simulation" ? { ...values, shipment_id: s.id } : values,
      values: { warehouse_id: s.warehouse_id, eta: s.eta, route: s.route },
      fields: [
        warehouseField(),
        { key: "route", label: "Route / via hub", minLength: 2 },
        { key: "eta", label: "Revised expected delivery", type: "date" },
        { key: "reason", label: "Reason", type: "textarea", minLength: 5 },
      ],
    });
  }
  function disruptionForm() {
    setModal({
      title: "Report disruption",
      subtitle:
        "Saves the disruption and runs the eight analysis steps to create a reviewable response plan.",
      path: "/disruptions",
      values: {
        severity: "HIGH",
        event_type: "SUPPLIER",
        estimated_impact_usd: 0,
        affected: "",
      },
      fields: [
        { key: "title", label: "Title", minLength: 5 },
        {
          key: "description",
          label: "Description",
          type: "textarea",
          minLength: 10,
        },
        selectField(
          "event_type",
          "Type",
          [
            "WEATHER",
            "GEOPOLITICAL",
            "SUPPLIER",
            "PORT",
            "DEMAND",
            "LOGISTICS",
          ].map((value) => ({ value, label: value })),
        ),
        selectField(
          "severity",
          "Severity",
          ["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((value) => ({
            value,
            label: value,
          })),
        ),
        {
          ...selectField(
            "affected",
            "Affected supplier (optional)",
            supplierOptions,
          ),
          required: false,
        },
        {
          key: "estimated_impact_usd",
          label: "Estimated exposure (USD)",
          type: "number",
          min: 0,
          step: "0.01",
        },
      ],
      transform: ({ affected, ...values }) => ({
        ...values,
        affected_entities: affected ? [affected] : [],
      }),
      submit: "Report & analyze",
    });
  }
  function reviewForm(d, approved) {
    setModal({
      title: approved ? "Approve response plan" : "Reject response plan",
      subtitle:
        d.action +
        (d.source === "simulation"
          ? ". Approval queues execution in the simulation ERP, followed by replanning."
          : ". This records a review; it does not contact a real vendor."),
      path: `/agents/decision/${d.id}/approve`,
      fields: [
        {
          key: "reason",
          label: "Review reason",
          type: "textarea",
          minLength: 5,
        },
      ],
      transform: (v) => ({ ...v, approved }),
      submit: approved ? "Approve plan" : "Reject plan",
    });
  }
  function resolveForm(d) {
    setModal({
      title: "Resolve disruption",
      subtitle: "Any pending plans for this disruption will be cancelled.",
      path: `/disruptions/${d.id}/resolve`,
      method: "PATCH",
      fields: [
        {
          key: "notes",
          label: "Resolution notes",
          type: "textarea",
          minLength: 5,
        },
      ],
      submit: "Mark resolved",
    });
  }
  function deliverForm(s) {
    setModal({
      title: `Receive ${s.tracking_number}`,
      subtitle: `Records delivery of ${n(s.quantity)} units into ${warehouseName(s.warehouse_id)}. Available capacity is checked before saving.`,
      path: `/shipments/${s.id}/deliver`,
      fields: [],
      transform: () => ({}),
      submit: "Confirm receipt",
    });
  }
  async function exportData() {
    try {
      const rows =
        view === "events"
          ? await api("/agents/audit-trail?limit=5000")
          : view === "forecast"
            ? (await api("/platform/forecasts")).points
            : data[view === "inventory" ? "warehouses" : view] || [k];
      if (!rows.length) {
        setToast("There are no records to export.");
        return;
      }
      const columns = [...new Set(rows.flatMap(Object.keys))];
      const cell = (v) => {
        const text =
          typeof v === "object" ? JSON.stringify(v) : String(v ?? "");
        return `"${(/^[=+\-@\t\r]/.test(text) ? "'" : "") + text.replace(/"/g, '""')}"`;
      };
      const csv = [
        columns.map(cell).join(","),
        ...rows.map((row) => columns.map((key) => cell(row[key])).join(",")),
      ].join("\r\n");
      const url = URL.createObjectURL(
        new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" }),
      );
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `nexus-${view}-${today()}.csv`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setToast("CSV exported.");
    } catch (e) {
      setError(e.message);
    }
  }
  async function importDemand(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 250000) throw new Error("Use a CSV smaller than 250 KB.");
      const lines = (await file.text())
        .replace(/^\uFEFF/, "")
        .trim()
        .split(/\r?\n/);
      if (lines.shift()?.trim().toLowerCase() !== "date,quantity")
        throw new Error(
          "CSV header must be date,quantity. Use one YYYY-MM-DD date and whole-unit quantity per line.",
        );
      const observations = lines.map((line) => {
        const [day, quantity, ...extra] = line.split(",");
        if (extra.length || !/^\d+$/.test(quantity?.trim() || ""))
          throw new Error(
            "Each row must have a date and a non-negative whole-number quantity.",
          );
        return { date: day.trim(), quantity: Number(quantity) };
      });
      await api("/forecast/history", { observations });
      saved("Demand history imported and forecast recalculated.");
    } catch (e) {
      setError(e.message);
    } finally {
      event.target.value = "";
    }
  }

  let content;
  if (view === "overview")
    content = (
      <>
        <div className="stats-grid">
          <Stat
            label="On-time delivery"
            value={k.on_time_delivery == null ? "—" : `${k.on_time_delivery}%`}
            detail={`${k.delivered_shipments} delivered shipments`}
            icon={Truck}
          />
          <Stat
            label="Network stock"
            value={n(k.total_stock)}
            detail={`${k.warehouse_utilization}% warehouse utilization`}
            icon={Boxes}
            tone="green"
          />
          <Stat
            label="Active disruptions"
            value={k.active_disruptions}
            detail={`${k.high_risk_suppliers} suppliers at elevated risk`}
            icon={AlertTriangle}
            tone="amber"
          />
          <Stat
            label="Plans awaiting review"
            value={k.pending_decisions}
            detail="Human oversight, complete audit history"
            icon={ClipboardCheck}
            tone="purple"
          />
        </div>
        <div className="overview-grid">
          <Panel
            title="Global supply network"
            subtitle={`${data.suppliers.length} suppliers · ${data.warehouses.length} warehouses`}
            action={
              <button className="text-button" onClick={() => navigate("twin")}>
                Explore network
                <ArrowUpRight size={15} />
              </button>
            }
          >
            <NetworkMap data={data} />
          </Panel>
          <Panel
            title="Attention queue"
            subtitle="Open exceptions across your network"
            action={<span className="count">{k.active_disruptions}</span>}
          >
            <div className="attention-list">
              {data.disruptions
                .filter((d) => d.status === "ACTIVE")
                .slice(0, 4)
                .map((d) => (
                  <button
                    key={d.id}
                    className="attention-item"
                    onClick={() => navigate("disruptions")}
                  >
                    <div>
                      <Badge value={d.severity} />
                      <small>{d.event_type}</small>
                    </div>
                    <strong>{d.title}</strong>
                    <span>
                      {usd(d.estimated_impact_usd)} estimated exposure
                      <ChevronRight size={15} />
                    </span>
                  </button>
                ))}
              {!k.active_disruptions && <Empty>No open disruptions.</Empty>}
            </div>
            <button className="panel-footer-button" onClick={disruptionForm}>
              <Plus size={15} />
              Report a disruption
            </button>
          </Panel>
        </div>
        <div className="two-columns">
          <Panel
            title="Demand outlook"
            subtitle={`${data.forecast.model} · ${data.forecast.data_source}`}
            action={
              <button
                className="text-button"
                onClick={() => navigate("forecast")}
              >
                View forecast
                <ArrowUpRight size={15} />
              </button>
            }
          >
            <ForecastChart forecast={data.forecast} />
          </Panel>
          <Panel
            title="Warehouse utilization"
            subtitle="Current stock as a percentage of capacity"
          >
            <div className="warehouse-bars">
              {data.warehouses.map((w) => (
                <div key={w.id}>
                  <span>{w.name}</span>
                  <div className="progress">
                    <i
                      style={{
                        width: `${Math.min(w.utilization, 100)}%`,
                        background: w.utilization >= 90 ? "#f4b56c" : "#57cbb7",
                      }}
                    />
                  </div>
                  <strong>{w.utilization}%</strong>
                </div>
              ))}
            </div>
          </Panel>
        </div>
        <Panel
          title="Recent activity"
          subtitle="Saved operations, refreshed every five seconds"
          action={
            <button className="text-button" onClick={() => navigate("events")}>
              All events
              <ArrowRight size={15} />
            </button>
          }
        >
          {data.events.slice(0, 4).map((e) => (
            <div className="activity-row" key={e.seq}>
              <div className="activity-icon">
                <Activity size={16} />
              </div>
              <div>
                <p>{e.message}</p>
                <small>{e.actor}</small>
              </div>
              <time>{dt(e.timestamp)}</time>
            </div>
          ))}
        </Panel>
      </>
    );
  if (view === "shipments")
    content = (
      <Panel
        title="Shipment register"
        subtitle={`${data.shipments.length} shipments · ${k.delayed_shipments} delayed or overdue`}
        action={
          <button className="button" onClick={shipmentForm}>
            <Plus size={16} />
            Create shipment
          </button>
        }
      >
        <Table
          rows={data.shipments
            .filter(matches)
            .filter((s) => filter === "ALL" || s.status === filter)}
          columns={[
            {
              label: "Tracking / carrier",
              render: (s) => (
                <>
                  <strong>{s.tracking_number}</strong>
                  <small>{s.carrier}</small>
                </>
              ),
            },
            {
              label: "Supply route",
              render: (s) => (
                <>
                  <span>{supplierName(s.supplier_id)}</span>
                  <small>
                    → {warehouseName(s.warehouse_id)} · {s.route}
                  </small>
                </>
              ),
            },
            { label: "Units", render: (s) => n(s.quantity) },
            {
              label: "ETA",
              render: (s) => (
                <>
                  <span>{s.eta}</span>
                  {s.status !== "DELIVERED" && s.eta < today() && (
                    <small className="text-amber">Overdue</small>
                  )}
                </>
              ),
            },
            { label: "Status", render: (s) => <Badge value={s.status} /> },
            {
              label: "Actions",
              render: (s) =>
                s.status !== "DELIVERED" ? (
                  <div className="row-actions">
                    <button onClick={() => rerouteForm(s)}>Reroute</button>
                    <button onClick={() => deliverForm(s)}>Receive</button>
                  </div>
                ) : (
                  <span className="text-muted">
                    Received {s.delivered_at.slice(0, 10)}
                  </span>
                ),
            },
          ]}
        />
      </Panel>
    );
  if (view === "inventory")
    content = (
      <>
        <div className="stats-grid three">
          <Stat
            label="Total network stock"
            value={n(k.total_stock)}
            detail="Units across all warehouses"
            icon={Boxes}
          />
          <Stat
            label="Network utilization"
            value={`${k.warehouse_utilization}%`}
            detail="Weighted by warehouse capacity"
            icon={Activity}
            tone="green"
          />
          <Stat
            label="Suggested transfers"
            value={data.recommendations.length}
            detail="Capacity-aware balance recommendations"
            icon={ArrowRight}
            tone="amber"
          />
        </div>
        <Panel
          title="Warehouse inventory"
          subtitle="Record a receipt from Shipments to add incoming stock"
          action={
            <div className="row-actions">
              <button
                className="button secondary"
                onClick={() =>
                  setModal({
                    title: "Add warehouse",
                    path: "/inventory/warehouses",
                    values: { stock: 0, lat: 0, lng: 0 },
                    fields: [
                      { key: "name", label: "Warehouse name", minLength: 2 },
                      {
                        key: "capacity",
                        label: "Capacity (units)",
                        type: "number",
                        min: 1,
                      },
                      {
                        key: "stock",
                        label: "Opening stock (units)",
                        type: "number",
                        min: 0,
                      },
                      {
                        key: "lat",
                        label: "Latitude",
                        type: "number",
                        min: -90,
                        max: 90,
                        step: "any",
                      },
                      {
                        key: "lng",
                        label: "Longitude",
                        type: "number",
                        min: -180,
                        max: 180,
                        step: "any",
                      },
                    ],
                  })
                }
              >
                <Plus size={15} />
                Warehouse
              </button>
              <button className="button" onClick={() => transferForm()}>
                <ArrowRight size={15} />
                Transfer stock
              </button>
            </div>
          }
        >
          <Table
            rows={data.warehouses.filter(matches)}
            columns={[
              {
                label: "Warehouse",
                render: (w) => (
                  <>
                    <strong>{w.name}</strong>
                    <small>{w.id}</small>
                  </>
                ),
              },
              { label: "Stock", render: (w) => n(w.stock) },
              { label: "Capacity", render: (w) => n(w.capacity) },
              {
                label: "Available space",
                render: (w) => n(w.capacity - w.stock),
              },
              {
                label: "Utilization",
                render: (w) => (
                  <div className="inline-progress">
                    <div className="progress">
                      <i style={{ width: `${w.utilization}%` }} />
                    </div>
                    {w.utilization}%
                  </div>
                ),
              },
              { label: "Status", render: (w) => <Badge value={w.status} /> },
            ]}
          />
        </Panel>
        <Panel
          title="Rebalancing recommendations"
          subtitle="Move stock out of warehouses above 80% occupancy. Review before recording."
        >
          {data.recommendations.length ? (
            data.recommendations.map((r, i) => (
              <div className="recommendation" key={i}>
                <div className="activity-icon">
                  <Boxes size={19} />
                </div>
                <div>
                  <strong>
                    {warehouseName(r.from_warehouse)} <ArrowRight size={14} />{" "}
                    {warehouseName(r.to_warehouse)}
                  </strong>
                  <p>
                    {n(r.quantity)} units · {r.reason}
                  </p>
                </div>
                <button
                  className="button secondary"
                  onClick={() => transferForm(r)}
                >
                  Review transfer
                </button>
              </div>
            ))
          ) : (
            <Empty>No capacity rebalancing needed.</Empty>
          )}
        </Panel>
      </>
    );
  if (view === "suppliers")
    content = (
      <>
        <div className="stats-grid">
          {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((level) => (
            <Stat
              key={level}
              label={`${level.toLowerCase()} risk`}
              value={
                data.suppliers.filter((s) => s.risk_level === level).length
              }
              detail="Suppliers in this risk band"
              icon={ShieldCheck}
              tone={
                level === "LOW"
                  ? "green"
                  : level === "MEDIUM"
                    ? "blue"
                    : "amber"
              }
            />
          ))}
        </div>
        <Panel
          title="Supplier directory"
          subtitle="Risk bands: low 0–24 · medium 25–49 · high 50–74 · critical 75–100"
          action={
            <button className="button" onClick={() => supplierForm()}>
              <Plus size={15} />
              Add supplier
            </button>
          }
        >
          <Table
            rows={data.suppliers
              .filter(matches)
              .filter((s) => filter === "ALL" || s.risk_level === filter)}
            columns={[
              {
                label: "Supplier",
                render: (s) => (
                  <>
                    <strong>{s.name}</strong>
                    <small>{s.id}</small>
                  </>
                ),
              },
              { label: "Country", render: (s) => s.country },
              { label: "Category", render: (s) => s.category },
              { label: "Risk", render: (s) => <Badge value={s.risk_level} /> },
              {
                label: "Score",
                render: (s) => (
                  <strong>
                    {s.risk_score}
                    <span className="text-muted"> / 100</span>
                  </strong>
                ),
              },
              { label: "Monthly volume", render: (s) => n(s.monthly_volume) },
              {
                label: "Manage",
                render: (s) => (
                  <button
                    className="text-button"
                    onClick={() => supplierForm(s)}
                  >
                    Edit
                    <ArrowUpRight size={14} />
                  </button>
                ),
              },
            ]}
          />
        </Panel>
      </>
    );
  if (view === "disruptions")
    content = (
      <Panel
        title="Disruption register"
        subtitle="Each report creates a saved response plan for human review"
        action={
          <button className="button" onClick={disruptionForm}>
            <Plus size={16} />
            Report disruption
          </button>
        }
      >
        <div className="disruption-list">
          {data.disruptions
            .filter(matches)
            .filter((d) => filter === "ALL" || d.status === filter)
            .map((d) => (
              <article className="disruption-card" key={d.id}>
                <div className="disruption-top">
                  <Badge value={d.severity} />
                  <span>{d.event_type}</span>
                  <Badge value={d.status} />
                </div>
                <h3>{d.title}</h3>
                <p>{d.description}</p>
                <div className="disruption-meta">
                  <span>{usd(d.estimated_impact_usd)} exposure</span>
                  <span>
                    {d.affected_entities.map(supplierName).join(", ") ||
                      "No linked entities"}
                  </span>
                  <time>{dt(d.detected_at)}</time>
                </div>
                {d.status === "ACTIVE" ? (
                  <div className="row-actions">
                    <button
                      className="button secondary"
                      onClick={async () => {
                        try {
                          await api(`/disruptions/${d.id}/analyze`, {});
                          saved("Response plan ready for review.");
                          navigate("decisions");
                        } catch (e) {
                          setError(e.message);
                        }
                      }}
                    >
                      <Cpu size={15} />
                      View response plan
                    </button>
                    <button
                      className="button secondary"
                      onClick={() => resolveForm(d)}
                    >
                      <Check size={15} />
                      Resolve
                    </button>
                  </div>
                ) : (
                  <p className="helper">Resolution: {d.resolution_notes}</p>
                )}
              </article>
            ))}
          {!data.disruptions
            .filter(matches)
            .filter((d) => filter === "ALL" || d.status === filter).length && (
            <Empty>No matching disruptions.</Empty>
          )}
        </div>
      </Panel>
    );
  if (view === "decisions")
    content = (
      <>
        <div className="notice">
          <ShieldCheck size={18} />
          <span>
            Simulation plan approvals publish execution events. The worker
            creates simulated purchase orders or updates shipments, then
            replans. No real vendor is contacted.
          </span>
        </div>
        <Panel
          title="Response plans"
          subtitle={`${k.pending_decisions} pending review · every review includes attribution and a reason`}
        >
          <div className="decision-list">
            {data.decisions
              .filter(matches)
              .filter((d) => filter === "ALL" || d.status === filter)
              .slice()
              .reverse()
              .map((d) => (
                <article key={d.id} className="decision-card">
                  <div className="decision-top">
                    <div className="activity-icon">
                      <Cpu size={18} />
                    </div>
                    <div>
                      <strong>{d.agent}</strong>
                      <small>
                        {d.id} · {dt(d.created_at)}
                      </small>
                    </div>
                    <Badge value={d.status} />
                  </div>
                  <h3>{d.action}</h3>
                  <p>{d.reasoning}</p>
                  <div className="decision-bottom">
                    <span>
                      Estimated exposure <strong>{usd(d.value_usd)}</strong>
                    </span>
                    {d.status === "PENDING" ? (
                      <div className="row-actions">
                        <button
                          className="button secondary"
                          onClick={() => reviewForm(d, false)}
                        >
                          Reject
                        </button>
                        <button
                          className="button"
                          onClick={() => reviewForm(d, true)}
                        >
                          <Check size={15} />
                          Approve plan
                        </button>
                      </div>
                    ) : (
                      <small>
                        Reviewed by {d.reviewed_by} · {dt(d.reviewed_at)}
                        <br />
                        {d.review_reason}
                      </small>
                    )}
                  </div>
                </article>
              ))}
            {!data.decisions
              .filter(matches)
              .filter((d) => filter === "ALL" || d.status === filter)
              .length && <Empty>No matching response plans.</Empty>}
          </div>
        </Panel>
      </>
    );
  if (view === "legacy-agents")
    content = (
      <>
        <div className="notice">
          <Cpu size={18} />
          <span>
            These are deterministic analysis steps, not trained AI agents.
            Report a disruption to run all eight steps. No API key is required.
          </span>
        </div>
        <div className="agent-grid">
          {data.agents.map((a, i) => (
            <article className="panel agent-card" key={a.id}>
              <div className="agent-card-top">
                <div className="activity-icon">
                  <Cpu size={22} />
                </div>
                <span className="eyebrow">
                  STEP {String(i + 1).padStart(2, "0")}
                </span>
                <Badge value={a.last_run ? "COMPLETED" : "READY"} />
              </div>
              <h3>{a.name}</h3>
              <p>{a.description}</p>
              <div className="agent-result">
                {a.result ||
                  "No analysis run yet. Report a disruption to generate a result."}
              </div>
              <small>
                {a.last_run
                  ? `Last run ${dt(a.last_run)}`
                  : "Waiting for a disruption report"}
              </small>
            </article>
          ))}
        </div>
      </>
    );
  if (view === "twin")
    content = (
      <>
        <Panel
          title="Connected supply network"
          subtitle="Select a location to inspect it. Links represent active recorded shipments."
        >
          <NetworkMap data={data} detailed />
        </Panel>
        <div className="stats-grid three">
          <Stat
            label="Supplier nodes"
            value={data.suppliers.length}
            detail="Operator-maintained locations"
            icon={Globe2}
          />
          <Stat
            label="Warehouse nodes"
            value={data.warehouses.length}
            detail="Inventory connected to shipment receipts"
            icon={Boxes}
            tone="green"
          />
          <Stat
            label="Active shipment links"
            value={k.active_shipments}
            detail="Includes rerouted and delayed shipments"
            icon={Truck}
            tone="purple"
          />
        </div>
      </>
    );
  if (view === "local-baseline")
    content = (
      <>
        <div className="notice">
          <CircleHelp size={18} />
          <span>
            {data.forecast.data_source === "sample"
              ? "This forecast uses seeded sample history."
              : "This forecast uses your imported demand history."}{" "}
            Baseline estimates and prediction ranges are statistical aids, not
            guarantees.
          </span>
        </div>
        <div className="stats-grid three">
          <Stat
            label="28-day baseline demand"
            value={n(
              data.forecast.points.reduce((sum, p) => sum + p.forecast, 0),
            )}
            detail="Forecast units across the workspace"
            icon={TrendingUp}
          />
          <Stat
            label="7-day backtest MAPE"
            value={
              data.forecast.backtest_mape == null
                ? "—"
                : `${data.forecast.backtest_mape}%`
            }
            detail="Held-out error; lower is better"
            icon={Activity}
            tone="green"
          />
          <Stat
            label="History through"
            value={data.forecast.as_of}
            detail="Forecast starts the following day"
            icon={ClipboardCheck}
            tone="purple"
          />
        </div>
        <Panel
          title="Demand forecast"
          subtitle={`${data.forecast.model} · ${data.forecast.interval}`}
          action={
            <button
              className="button secondary"
              onClick={() =>
                setModal({
                  title: "Replace demand history",
                  subtitle:
                    "This replaces the workspace demand series. Select a CSV with header date,quantity and 14–3,650 consecutive daily observations before today. Forecasts will be recalculated.",
                  custom: "import",
                })
              }
            >
              <ArrowDownToLine size={15} />
              Import history
            </button>
          }
        >
          <ForecastChart forecast={data.forecast} />
          <div className="map-legend">
            <span>
              <i className="dot blue" />
              Historical demand
            </span>
            <span>
              <i className="dot green" />
              Baseline forecast
            </span>
            <span>Shaded: approximate 90% prediction range</span>
          </div>
        </Panel>
        <Panel title="Daily planning values">
          <Table
            rows={data.forecast.points}
            rowKey="date"
            columns={[
              { label: "Date", render: (p) => p.date },
              { label: "Lower range", render: (p) => n(p.lower) },
              {
                label: "Baseline units",
                render: (p) => <strong>{n(p.forecast)}</strong>,
              },
              { label: "Upper range", render: (p) => n(p.upper) },
            ]}
          />
        </Panel>
      </>
    );
  if (view === "events")
    content = (
      <Panel
        title="Operational activity"
        subtitle="Latest 100 events · export includes up to 5,000 most recent events"
      >
        <div className="event-list">
          {data.events
            .filter(matches)
            .filter((e) => filter === "ALL" || e.type === filter)
            .map((e) => (
              <div className="event-row" key={e.seq}>
                <span className="event-seq">
                  {String(e.seq).padStart(4, "0")}
                </span>
                <Badge value={e.type} />
                <div>
                  <strong>{e.message}</strong>
                  <small>
                    {e.actor} · {e.entity_id || "workspace"}
                  </small>
                  {e.details?.reason && <p>{e.details.reason}</p>}
                </div>
                <time>{dt(e.timestamp)}</time>
              </div>
            ))}
          {!data.events
            .filter(matches)
            .filter((e) => filter === "ALL" || e.type === filter).length && (
            <Empty>No matching events.</Empty>
          )}
        </div>
      </Panel>
    );
  if (view === "copilot") content = <Copilot />;

  if (["platform", "agents", "forecast"].includes(view))
    content = (
      <PlatformWorkspace
        key={view}
        initialTab={view === "platform" ? "data" : view}
        onChanged={refresh}
      />
    );

  const filters = {
    shipments: ["IN_TRANSIT", "DELAYED", "REROUTED", "DELIVERED"],
    suppliers: ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    disruptions: ["ACTIVE", "RESOLVED"],
    decisions: [
      "PENDING",
      "APPROVED",
      "AUTO_APPROVED",
      "EXECUTED",
      "BLOCKED",
      "REJECTED",
      "CANCELLED",
    ],
    events: [...new Set(data.events.map((e) => e.type))],
  }[view];
  const searchable = [
    "shipments",
    "inventory",
    "suppliers",
    "disruptions",
    "decisions",
    "events",
  ].includes(view);
  return (
    <div className="app-shell">
      <aside className={`sidebar ${menu ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Network size={24} />
          </div>
          <span>
            NEXUS<span className="brand-sub">CONTROL TOWER</span>
          </span>
        </div>
        <div className="workspace-label">
          <span className="workspace-avatar">N</span>
          <div>
            NEXUS workspace<small>Operations platform</small>
          </div>
          <ChevronRight size={16} />
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav>
          {NAV.map(([id, label, Icon]) => (
            <button
              key={id}
              className={view === id ? "active" : ""}
              onClick={() => navigate(id)}
              aria-current={view === id ? "page" : undefined}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === "decisions" && k.pending_decisions > 0 && (
                <span className="nav-count">{k.pending_decisions}</span>
              )}
              {id === "copilot" && <span className="ai-tag">ARIA</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection">
            <i className={`dot ${error ? "amber" : "green"}`} />
            {error ? "Connection needs attention" : "Workspace connected"}
          </div>
          <p>
            Persisted operations · Sample & simulation
            <br />
            No external orders executed
          </p>
          <div className="account">
            <span className="avatar">{user.email[0].toUpperCase()}</span>
            <div>
              <strong>{user.email}</strong>
              <small>Workspace owner</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                try {
                  await api("/auth/logout", {});
                  setUser(null);
                  setData(null);
                } catch (e) {
                  setError(e.message);
                }
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      {menu && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={21} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{NAV.find((x) => x[0] === view)?.[1]}</strong>
          </div>
          <div>
            <span className="live-label">
              <i className={`dot ${error ? "amber" : "green"}`} />
              {error ? "STALE DATA" : "LIVE WORKSPACE"}
            </span>
            <span className="topbar-date">
              {new Date().toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
            <span className="avatar small">{user.email[0].toUpperCase()}</span>
          </div>
        </header>
        <main className="main-content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">OPERATIONS / {view.toUpperCase()}</span>
              <h1>{NAV.find((x) => x[0] === view)?.[1]}</h1>
              <p>{DESCRIPTIONS[view]}</p>
            </div>
            <div className="row-actions">
              <button
                className="button secondary icon-only"
                aria-label="Refresh workspace"
                onClick={refresh}
                disabled={refreshing}
              >
                <RefreshCw size={17} className={refreshing ? "spin" : ""} />
              </button>
              {!["copilot", "platform", "agents"].includes(view) && (
                <button className="button secondary" onClick={exportData}>
                  <ArrowDownToLine size={16} />
                  Export CSV
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="notice error" role="alert">
              <AlertTriangle size={18} />
              <span>{error} Displayed data may be out of date.</span>
              <button className="text-button" onClick={refresh}>
                Retry
              </button>
            </div>
          )}
          {searchable && (
            <div className="toolbar">
              <div className="search-field">
                <Search size={17} />
                <input
                  aria-label={`Search ${view}`}
                  placeholder={`Search ${view}…`}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                {query && (
                  <button
                    className="icon-button"
                    aria-label="Clear search"
                    onClick={() => setQuery("")}
                  >
                    <X size={14} />
                  </button>
                )}
              </div>
              {filters && (
                <select
                  aria-label="Filter records"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option value="ALL">All statuses / types</option>
                  {filters.map((f) => (
                    <option key={f} value={f}>
                      {f.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
          <div className="view-content">{content}</div>
          <footer className="page-footer">
            <span>NEXUS · Supply chain simulation platform</span>
            <span>Last synchronized {dt(data.generated_at)}</span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
          <button
            className="icon-button"
            onClick={() => setToast("")}
            aria-label="Dismiss notification"
          >
            <X size={15} />
          </button>
        </div>
      )}
      {modal && modal.custom !== "import" && (
        <RecordForm
          key={modal.path + modal.title}
          config={modal}
          close={closeModal}
          onSaved={saved}
        />
      )}{" "}
      {modal?.custom === "import" && (
        <Modal title={modal.title} subtitle={modal.subtitle} close={closeModal}>
          <div className="padded">
            <pre className="csv-example">
              date,quantity{"\n"}2026-01-01,1250{"\n"}2026-01-02,1310{"\n"}…
            </pre>
            <button
              className="button"
              onClick={() => {
                closeModal();
                demandFile.current?.click();
              }}
            >
              Choose CSV & replace history
            </button>
          </div>
        </Modal>
      )}
      <input
        type="file"
        ref={demandFile}
        accept=".csv,text/csv"
        hidden
        onChange={importDemand}
      />
    </div>
  );
}

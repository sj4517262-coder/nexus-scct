// ═══════════════════════════════════════════════════════════
// NEXUS Supply Chain Control Tower — TypeScript Type System
// frontend/lib/types.ts
// ═══════════════════════════════════════════════════════════

// ─── Core Enums ────────────────────────────────────────────
export type SeverityLevel   = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type DisruptionType  = "WEATHER" | "GEOPOLITICAL" | "SUPPLIER" | "PORT" | "DEMAND" | "LOGISTICS";
export type AgentStatus     = "ACTIVE" | "PROCESSING" | "IDLE" | "ALERT" | "ERROR";
export type DecisionStatus  = "PROPOSED" | "AUTO_APPROVED" | "PENDING" | "HUMAN_REQUIRED" | "HUMAN_APPROVED" | "HUMAN_REJECTED" | "EXECUTED" | "FAILED";
export type TransportMode   = "SEA" | "AIR" | "RAIL" | "ROAD";
export type WarehouseStatus = "OPTIMAL" | "WARNING" | "CRITICAL";
export type RiskLevel       = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type UserRole        = "VIEWER" | "OPERATOR" | "MANAGER" | "EXECUTIVE" | "ADMIN";

// ─── Disruption ─────────────────────────────────────────────
export interface Disruption {
  id:                  string;
  event_id:            string;
  event_type:          DisruptionType;
  severity:            SeverityLevel;
  title:               string;
  description:         string;
  affected_entities:   string[];
  estimated_impact_usd?: number;
  status:              "ACTIVE" | "MONITORING" | "ESCALATED" | "RESOLVED";
  detected_at:         string;
  resolved_at?:        string;
  orchestration_id?:   string;
  age?:                string;
}

export interface DisruptionCreate {
  event_type:          DisruptionType;
  severity:            SeverityLevel;
  title:               string;
  description:         string;
  affected_entities?:  string[];
  estimated_impact_usd?: number;
}

// ─── Supplier ───────────────────────────────────────────────
export interface Supplier {
  id:                     string;
  name:                   string;
  country:                string;
  region:                 "APAC" | "EMEA" | "LATAM" | "Americas";
  category:               string;
  risk_level:             RiskLevel;
  risk_score:             number;   // 0-100 (higher = healthier)
  on_time_delivery_rate:  number;   // 0-1
  monthly_volume:         number;
  annual_spend_usd:       number;
  tier:                   1 | 2 | 3;
  certifications:         string[];
  key_risk_factors:       string[];
  recommended_actions:    string[];
  last_scored_at:         string;
  lat?:                   number;
  lng?:                   number;
}

export interface SupplierRiskDetail extends Supplier {
  risk_history:      Array<{ date: string; score: number }>;
  dependency_graph:  { direct_products: number; sole_source_items: number; cascading_risk_items: number };
  alternative_suppliers: Array<{
    id: string; name: string; risk_score: number;
    lead_time_delta_days: number; cost_delta_pct: number;
  }>;
}

// ─── Warehouse ──────────────────────────────────────────────
export interface Warehouse {
  id:                       string;
  name:                     string;
  city:                     string;
  region:                   string;
  country:                  string;
  capacity_units:           number;
  current_inventory_units:  number;
  utilization_pct:          number;
  status:                   WarehouseStatus;
  reorder_point_units:      number;
  safety_stock_units:       number;
  stockout_probability:     number;
  days_of_supply:           number;
  lat?:                     number;
  lng?:                     number;
}

export interface RebalanceRecommendation {
  from_warehouse:     string;
  to_warehouse:       string;
  quantity:           number;
  sku_category:       string;
  estimated_cost_usd: number;
  confidence:         number;
  urgency:            SeverityLevel;
  ai_reasoning:       string;
}

// ─── AI Agent ───────────────────────────────────────────────
export interface AgentStatus {
  id:               string;
  name:             string;
  status:           AgentStatus;
  decisions_today:  number;
  confidence_avg:   number;
  current_task:     string;
  last_decision_at: string;
  color?:           string;
}

export interface AgentDecision {
  id:               string;
  agent:            string;
  action:           string;
  confidence:       number;
  status:           DecisionStatus;
  value_usd?:       number;
  timestamp:        string;
  reasoning:        string;
  alternatives_considered?: string[];
}

export interface ApprovalRequest {
  approved:        boolean;
  reason?:         string;
  approver_notes?: string;
}

export interface AuditTrailEntry {
  timestamp:   string;
  decision_id: string;
  agent:       string;
  action:      string;
  value_usd?:  number;
  approver?:   string;
  confidence:  number;
  outcome:     string;
  impact?:     string;
}

// ─── KPIs ───────────────────────────────────────────────────
export interface RealtimeKPIs {
  otif:                    number;
  fill_rate:               number;
  inventory_turnover:      number;
  warehouse_utilization:   number;
  transport_cost_per_unit: number;
  stockout_probability:    number;
  supplier_reliability:    number;
  delay_risk:              number;
  ai_decisions_today:      number;
  ai_auto_approve_rate:    number;
  active_disruptions:      number;
  pending_approvals:       number;
  timestamp:               string;
}

export interface KPIBenchmark {
  name:       string;
  current:    number;
  target:     number;
  threshold:  number;
  status:     "ABOVE_TARGET" | "ON_TRACK" | "ABOVE_THRESHOLD" | "BELOW_THRESHOLD" | "OPTIMAL";
  trend:      "IMPROVING" | "STABLE" | "DECLINING";
}

export interface KPITrends {
  period:      string;
  data_points: number;
  otif:        number[];
  fill_rate:   number[];
  warehouse_utilization: number[];
  generated_at: string;
}

// ─── Shipment ───────────────────────────────────────────────
export interface Shipment {
  id:               string;
  tracking_number:  string;
  supplier_id:      string;
  supplier_name:    string;
  destination_warehouse_id: string;
  destination_city: string;
  origin_country:   string;
  origin_port:      string;
  carrier:          string;
  transport_mode:   TransportMode;
  status:           "IN_TRANSIT" | "AT_PORT" | "CUSTOMS" | "DELIVERED" | "DELAYED" | "EXCEPTION";
  category:         string;
  quantity_units:   number;
  weight_kg:        number;
  value_usd:        number;
  origin_date:      string;
  eta:              string;
  actual_arrival?:  string;
  delay_days:       number;
  is_delayed:       boolean;
  delay_risk_score: number;
  last_event:       string;
}

// ─── Event Stream ───────────────────────────────────────────
export interface StreamEvent {
  t:       string;
  type:    "DISRUPTION" | "DECISION" | "ALERT" | "RISK" | "OPTIMIZATION" | "FORECAST" | "ESCALATION" | "UPDATE";
  sev:     SeverityLevel;
  msg:     string;
  agent:   string;
}

// ─── Auth ───────────────────────────────────────────────────
export interface AuthToken {
  access_token:  string;
  refresh_token: string;
  token_type:    "bearer";
  expires_in:    number;
  user: {
    id:    string;
    email: string;
    name:  string;
    role:  UserRole;
  };
}

// ─── API Response Wrappers ──────────────────────────────────
export interface PaginatedResponse<T> {
  items:   T[];
  total:   number;
  page:    number;
  pages:   number;
  limit:   number;
  offset:  number;
}

export interface ApiError {
  error:           string;
  message:         string;
  correlation_id?: string;
  details?:        Record<string, string[]>;
}

// ─── Chart Data ─────────────────────────────────────────────
export interface ForecastDataPoint {
  d:        string;
  actual?:  number | null;
  forecast: number;
  hi:       number;
  lo:       number;
}

export interface KPIHistoryPoint {
  h:    string;
  otif: number;
  fill: number;
  util: number;
}


// ═══════════════════════════════════════════════════════════
// frontend/lib/api-client.ts
// Typed API client with React Query integration
// ═══════════════════════════════════════════════════════════

import { useQuery, useMutation, useQueryClient, UseQueryResult } from "@tanstack/react-query";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Base fetch with auth
async function apiFetch<T>(
  path:    string,
  options: RequestInit = {},
): Promise<T> {
  const token = typeof window !== "undefined"
    ? localStorage.getItem("nexus_access_token")
    : null;

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({
      error: "Network error",
      message: `Request failed: ${response.status} ${response.statusText}`,
    }));
    throw new Error(error.message || `API error: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// ─── Query Keys ─────────────────────────────────────────────
export const queryKeys = {
  kpis:           () => ["kpis", "realtime"],
  kpiTrends:      (period: string) => ["kpis", "trends", period],
  kpiBenchmarks:  () => ["kpis", "benchmarks"],
  disruptions:    (filters?: Record<string, string>) => ["disruptions", filters],
  disruption:     (id: string) => ["disruptions", id],
  suppliers:      (filters?: Record<string, string>) => ["suppliers", filters],
  supplier:       (id: string) => ["suppliers", id],
  supplierRisk:   (id: string) => ["suppliers", id, "risk"],
  warehouses:     () => ["inventory", "warehouses"],
  rebalance:      () => ["inventory", "rebalance"],
  alerts:         () => ["inventory", "alerts"],
  agents:         () => ["agents", "status"],
  decisions:      (status?: string) => ["agents", "decisions", status],
  auditTrail:     () => ["agents", "audit-trail"],
  shipments:      () => ["shipments"],
  forecast:       () => ["forecast"],
} as const;

// ─── KPI Hooks ──────────────────────────────────────────────
export function useRealtimeKPIs(refetchInterval = 10_000): UseQueryResult<RealtimeKPIs> {
  return useQuery({
    queryKey: queryKeys.kpis(),
    queryFn: () => apiFetch<RealtimeKPIs>("/api/v1/kpis/realtime"),
    refetchInterval,
    staleTime: 5_000,
  });
}

export function useKPITrends(period: "24h" | "7d" | "30d" | "90d" = "24h") {
  return useQuery({
    queryKey: queryKeys.kpiTrends(period),
    queryFn: () => apiFetch<KPITrends>(`/api/v1/kpis/trends?period=${period}`),
    staleTime: 60_000,
  });
}

export function useKPIBenchmarks() {
  return useQuery({
    queryKey: queryKeys.kpiBenchmarks(),
    queryFn: () => apiFetch<{ kpis: KPIBenchmark[]; overall_health_score: number }>("/api/v1/kpis/benchmarks"),
    staleTime: 120_000,
  });
}

// ─── Disruption Hooks ───────────────────────────────────────
export function useDisruptions(filters?: Record<string, string>) {
  const params = filters ? `?${new URLSearchParams(filters)}` : "";
  return useQuery({
    queryKey: queryKeys.disruptions(filters),
    queryFn: () => apiFetch<Disruption[]>(`/api/v1/disruptions${params}`),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function useCreateDisruption() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (disruption: DisruptionCreate) =>
      apiFetch("/api/v1/disruptions", { method: "POST", body: JSON.stringify(disruption) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["disruptions"] });
      qc.invalidateQueries({ queryKey: queryKeys.kpis() });
      qc.invalidateQueries({ queryKey: queryKeys.agents() });
    },
  });
}

export function useResolveDisruption() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) =>
      apiFetch(`/api/v1/disruptions/${id}/resolve`, {
        method: "PATCH",
        body: JSON.stringify({ resolution_notes: notes }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["disruptions"] }),
  });
}

// ─── Supplier Hooks ─────────────────────────────────────────
export function useSuppliers(filters?: Record<string, string>) {
  const params = filters ? `?${new URLSearchParams(filters)}` : "";
  return useQuery({
    queryKey: queryKeys.suppliers(filters),
    queryFn: () => apiFetch<{ suppliers: Supplier[]; total: number }>(`/api/v1/suppliers${params}`),
    staleTime: 60_000,
  });
}

export function useSupplierRisk(supplierId: string) {
  return useQuery({
    queryKey: queryKeys.supplierRisk(supplierId),
    queryFn: () => apiFetch<SupplierRiskDetail>(`/api/v1/suppliers/${supplierId}/risk`),
    enabled: !!supplierId,
    staleTime: 120_000,
  });
}

export function useRescoreSupplier() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (supplierId: string) =>
      apiFetch(`/api/v1/suppliers/${supplierId}/risk/rescore`, { method: "POST" }),
    onSuccess: (_: unknown, supplierId: string) => {
      qc.invalidateQueries({ queryKey: queryKeys.supplierRisk(supplierId) });
    },
  });
}

// ─── Inventory Hooks ────────────────────────────────────────
export function useInventoryStatus() {
  return useQuery({
    queryKey: queryKeys.warehouses(),
    queryFn: () => apiFetch<Warehouse[]>("/api/v1/inventory"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useRebalanceRecommendations() {
  return useQuery({
    queryKey: queryKeys.rebalance(),
    queryFn: () => apiFetch<RebalanceRecommendation[]>("/api/v1/inventory/rebalance-recommendations"),
    staleTime: 120_000,
  });
}

export function useTriggerOptimization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { warehouse_ids: string[]; optimization_type: string; urgency: string }) =>
      apiFetch("/api/v1/inventory/optimize", { method: "POST", body: JSON.stringify(params) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.warehouses() }),
  });
}

// ─── Agent Hooks ────────────────────────────────────────────
export function useAgentStatus() {
  return useQuery({
    queryKey: queryKeys.agents(),
    queryFn: () => apiFetch<{ agents: AgentStatus[]; summary: Record<string, number | string> }>("/api/v1/agents/status"),
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

export function useAgentDecisions(status?: string) {
  const params = status ? `?status=${status}` : "";
  return useQuery({
    queryKey: queryKeys.decisions(status),
    queryFn: () => apiFetch<{ decisions: AgentDecision[]; total: number; pending_human_approval: number }>(
      `/api/v1/agents/decisions${params}`
    ),
    refetchInterval: 20_000,
    staleTime: 10_000,
  });
}

export function useApproveDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ decisionId, approval }: { decisionId: string; approval: ApprovalRequest }) =>
      apiFetch(`/api/v1/agents/decision/${decisionId}/approve`, {
        method: "POST",
        body: JSON.stringify(approval),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.decisions() });
      qc.invalidateQueries({ queryKey: queryKeys.auditTrail() });
      qc.invalidateQueries({ queryKey: queryKeys.kpis() });
    },
  });
}

export function useAuditTrail(filters?: { start_date?: string; end_date?: string }) {
  const params = filters ? `?${new URLSearchParams(filters as Record<string, string>)}` : "";
  return useQuery({
    queryKey: queryKeys.auditTrail(),
    queryFn: () => apiFetch<{
      audit_entries: AuditTrailEntry[];
      total_entries: number;
      auto_approved_count: number;
      human_approved_count: number;
    }>(`/api/v1/agents/audit-trail${params}`),
    staleTime: 60_000,
  });
}

// ─── WebSocket Hook ─────────────────────────────────────────
import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export function useEventStream(maxEvents = 50) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/ws/events`);
    wsRef.current = ws;

    ws.onopen    = () => setConnected(true);
    ws.onclose   = () => { setConnected(false); setTimeout(connect, 3000); };
    ws.onerror   = () => ws.close();
    ws.onmessage = (e) => {
      try {
        const event: StreamEvent = JSON.parse(e.data);
        if (event.type === "heartbeat") return;
        setEvents((prev) => [event, ...prev].slice(0, maxEvents));
      } catch {}
    };
  }, [maxEvents]);

  useEffect(() => {
    connect();
    return () => { wsRef.current?.close(); };
  }, [connect]);

  return { events, connected };
}

export function useKPIStream() {
  const [kpis, setKPIs] = useState<Partial<RealtimeKPIs>>({});
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}/ws/kpis`);
    wsRef.current = ws;
    ws.onopen    = () => setConnected(true);
    ws.onclose   = () => setConnected(false);
    ws.onmessage = (e) => {
      try { setKPIs(JSON.parse(e.data)); } catch {}
    };
    return () => ws.close();
  }, []);

  return { kpis, connected };
}

// ─── Utility Hooks ──────────────────────────────────────────
export function useHealthCheck() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<{ status: string; version: string; checks: Record<string, boolean> }>("/health"),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: 1,
  });
}

export function usePlatformStats() {
  const kpis = useRealtimeKPIs();
  const disruptions = useDisruptions();
  const agents = useAgentStatus();
  const decisions = useAgentDecisions("HUMAN_REQUIRED");

  return {
    isLoading: kpis.isLoading || disruptions.isLoading || agents.isLoading,
    activeDisruptions: disruptions.data?.length ?? 0,
    criticalDisruptions: disruptions.data?.filter((d) => d.severity === "CRITICAL").length ?? 0,
    activeAgents: agents.data?.summary?.active ?? 0,
    pendingApprovals: decisions.data?.pending_human_approval ?? 0,
    otif: kpis.data?.otif ?? 0,
    fillRate: kpis.data?.fill_rate ?? 0,
  };
}

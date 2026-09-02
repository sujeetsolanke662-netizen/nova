import type {
  AuditLogEntry,
  AuditVerifyResponse,
  ClutterFinding,
  CopilotAskResponse,
  ForecastResponse,
  GuardrailsCheckResponse,
  HealthResponse,
  QuarantineEntry,
  RecommendationsResponse,
  UsageSnapshot,
} from '@/types/nova'

/**
 * Requests go through Vite's dev-server proxy (see vite.config.ts) so the
 * browser only ever talks to same-origin `/api/*` and `/health` — the
 * FastAPI backend has no CORS middleware configured, and NOVA is meant to
 * run fully offline, so we never point this at a cross-origin URL.
 */
const BASE_URL = ''

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(pathname: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${pathname}`, init)
  } catch {
    throw new ApiError(
      'Could not reach the NOVA backend. Confirm the service is running and reachable.',
      0,
    )
  }

  if (!response.ok) {
    let detail: string | undefined
    try {
      const body = (await response.clone().json()) as { detail?: string }
      detail = body.detail
    } catch {
      // Non-JSON error body — fall back to the status text below.
    }
    throw new ApiError(
      detail ?? `Request to ${pathname} failed with status ${response.status}`,
      response.status,
    )
  }

  return response.json() as Promise<T>
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  guardrailsCheck: (path: string) =>
    request<GuardrailsCheckResponse>(`/api/guardrails/check?${new URLSearchParams({ path })}`),

  aptClutterScan: () => request<ClutterFinding[]>('/api/apt-clutter/scan'),

  auditLog: () => request<AuditLogEntry[]>('/api/audit-log'),

  auditLogVerify: () => request<AuditVerifyResponse>('/api/audit-log/verify'),

  recommendations: (root: string) =>
    request<RecommendationsResponse>(`/api/recommendations?${new URLSearchParams({ root })}`),

  quarantineList: () => request<QuarantineEntry[]>('/api/quarantine'),

  quarantineFile: (path: string, reason: string) =>
    request<QuarantineEntry>('/api/quarantine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, reason }),
    }),

  quarantineRestore: (quarantineId: string) =>
    request<QuarantineEntry>(`/api/quarantine/${encodeURIComponent(quarantineId)}/restore`, {
      method: 'POST',
    }),

  copilotAsk: (question: string, root: string) =>
    request<CopilotAskResponse>('/api/copilot/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, root }),
    }),

  forecast: (path: string) =>
    request<ForecastResponse>(`/api/forecast?${new URLSearchParams({ path })}`),

  forecastSnapshot: (path: string) =>
    request<UsageSnapshot>('/api/forecast/snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    }),
}

/**
 * Shapes mirror backend/app/main.py's response bodies exactly. Keep these in
 * sync with the FastAPI handlers by hand — there is no shared schema/OpenAPI
 * codegen wired up yet.
 */

export interface HealthResponse {
  status: string
}

export type GuardrailClassification = 'protected' | 'outside_scan_scope' | 'reviewable'

export interface GuardrailsCheckResponse {
  path: string
  classification: GuardrailClassification
  reason: string | null
}

// backend/app/apt_clutter.py's four category constants.
export type ClutterCategory =
  | 'stale_deb_cache'
  | 'orphaned_config_file'
  | 'old_kernel'
  | 'orphaned_package'

export interface ClutterFinding {
  category: ClutterCategory
  description: string
  estimated_size_bytes: number
  safe_to_auto_apply: boolean
  target_paths: string[]
}

export type AuditActionType =
  | 'recommend'
  | 'guardrail_block'
  | 'auto_apply'
  | 'quarantine'
  | 'restore'
  | string

export interface AuditLogEntry {
  entry_id: number
  timestamp: string
  action_type: AuditActionType
  target_paths: string[]
  reason: string
  actor: string
  prev_hash: string
  entry_hash: string
}

export interface AuditVerifyResponse {
  valid: boolean
  broken_at_entry: number | null
}

// backend/app/recommendation.py's AUTO_APPLY/REVIEW_RECOMMENDED/KEEP constants.
export type RecommendedAction = 'auto_apply' | 'review_recommended' | 'keep'

// backend/app/staleness.py's score_staleness() factor breakdown.
export interface StalenessFactor {
  name: string
  contribution: number
  explanation: string
}

export interface RecommendationItem {
  path: string
  recommended_action: RecommendedAction
  staleness_score: number
  factors: StalenessFactor[]
  duplicate_of: string | null
  near_duplicate_of: string[] | null
}

export interface RecommendationsResponse {
  scanned_count: number
  skipped_count: number
  protected_count: number
  recommendations: RecommendationItem[]
}

// backend/app/quarantine.py's STATUS_* constants.
export type QuarantineStatus = 'quarantined' | 'restored' | 'purged'

export interface QuarantineEntry {
  quarantine_id: string
  original_path: string
  quarantined_path: string
  quarantined_at: string
  reason: string
  status: QuarantineStatus
}

// backend/app/copilot_answer.py's generate_answer()/answer_query() return shape.
export interface CopilotAskResponse {
  answer_text: string
  cited_paths: string[]
  intent: string
}

// backend/app/forecasting.py's get_disk_usage() shape.
export interface DiskUsage {
  total_bytes: number
  used_bytes: number
  free_bytes: number
  used_percent: number
}

// forecast_capacity()'s "ok" branch. The projected-usage key's day count is
// hardcoded by /api/forecast (forecast_capacity's days_ahead default, 30 -
// the endpoint never overrides it), so the key name is stable as long as
// that stays true.
export interface ForecastOk {
  status: 'ok'
  current_used_percent: number
  projected_used_percent_in_30_days: number
  trend_bytes_per_day: number
  days_until_full: number | null
}

export interface ForecastInsufficientData {
  status: 'insufficient_data'
  snapshots_available: number
  snapshots_needed: number
}

// /api/forecast returns {**get_disk_usage(path), **forecast_capacity(path)}.
export type ForecastResponse = DiskUsage & (ForecastOk | ForecastInsufficientData)

// record_usage_snapshot()'s return shape (POST /api/forecast/snapshot).
export interface UsageSnapshot {
  path: string
  used_bytes: number
  total_bytes: number
  used_percent: number
  timestamp: string
}

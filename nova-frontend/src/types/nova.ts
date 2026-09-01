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

export type AuditActionType = 'recommend' | 'guardrail_block' | string

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

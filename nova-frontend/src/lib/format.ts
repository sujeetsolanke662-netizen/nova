import { Archive, Eye, Info, Minus, RotateCcw, ShieldAlert, Zap, type LucideIcon } from 'lucide-react'
import type { ClutterFinding } from '@/types/nova'

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 B'

  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), BYTE_UNITS.length - 1)
  const value = bytes / 1024 ** exponent
  const precision = exponent === 0 ? 0 : value < 10 ? 2 : 1

  return `${value.toFixed(precision)} ${BYTE_UNITS[exponent]}`
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date)
}

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso

  const diffSeconds = (date.getTime() - Date.now()) / 1000
  const divisions: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 60 * 60 * 24 * 365],
    ['month', 60 * 60 * 24 * 30],
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
    ['second', 1],
  ]

  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  for (const [unit, secondsInUnit] of divisions) {
    if (Math.abs(diffSeconds) >= secondsInUnit || unit === 'second') {
      return formatter.format(Math.round(diffSeconds / secondsInUnit), unit)
    }
  }
  return formatter.format(0, 'second')
}

export function truncatePath(path: string, maxLength = 56): string {
  if (path.length <= maxLength) return path
  const keep = Math.floor((maxLength - 1) / 2)
  return `${path.slice(0, keep)}…${path.slice(path.length - keep)}`
}

const CLUTTER_CATEGORY_LABELS: Record<string, string> = {
  stale_deb_cache: 'Stale package cache',
  orphaned_config_file: 'Orphaned config file',
  old_kernel: 'Old kernel',
  orphaned_package: 'Orphaned package',
}

export function formatClutterCategory(category: string): string {
  return CLUTTER_CATEGORY_LABELS[category] ?? category.replace(/_/g, ' ')
}

// Plural, heading-style labels for the grouped cleanup list - distinct from
// formatClutterCategory's singular per-row label above.
const CLUTTER_CATEGORY_GROUP_LABELS: Record<string, string> = {
  stale_deb_cache: 'Stale Cache Files',
  orphaned_config_file: 'Orphaned Configs',
  old_kernel: 'Old Kernels',
  orphaned_package: 'Orphaned Packages',
}

export function formatClutterCategoryGroup(category: string): string {
  return CLUTTER_CATEGORY_GROUP_LABELS[category] ?? formatClutterCategory(category)
}

/** Stable identity for a finding - no server-issued id exists for these. */
export function clutterFindingKey(finding: ClutterFinding): string {
  return `${finding.category}:${finding.target_paths.join(',')}`
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  recommend: 'Recommendation',
  guardrail_block: 'Guardrail block',
  auto_apply: 'Auto-applied',
  quarantine: 'Quarantine',
  restore: 'Restore',
}

export function formatActionType(actionType: string): string {
  return ACTION_TYPE_LABELS[actionType] ?? actionType.replace(/_/g, ' ')
}

type ActionBadgeTone = 'neutral' | 'brand' | 'auto' | 'success' | 'warning' | 'danger'

// Canonical hierarchy (see Badge.tsx): recommend/keep are routine, quarantine
// is a user-invoked action, auto_apply is the system acting on its own,
// restore is a positive/reversible resolution, and guardrail_block is the
// single highest-weight negative trust signal in the app.
const ACTION_TYPE_TONES: Record<string, ActionBadgeTone> = {
  recommend: 'neutral',
  guardrail_block: 'danger',
  auto_apply: 'auto',
  quarantine: 'brand',
  restore: 'success',
}

const ACTION_TYPE_ICONS: Record<string, LucideIcon> = {
  recommend: Info,
  guardrail_block: ShieldAlert,
  auto_apply: Zap,
  quarantine: Archive,
  restore: RotateCcw,
}

export function actionTypeTone(actionType: string): ActionBadgeTone {
  return ACTION_TYPE_TONES[actionType] ?? 'neutral'
}

export function actionTypeIcon(actionType: string): LucideIcon | undefined {
  return ACTION_TYPE_ICONS[actionType]
}

const RECOMMENDED_ACTION_LABELS: Record<string, string> = {
  auto_apply: 'Auto-apply',
  review_recommended: 'Review',
  keep: 'Keep',
}

export function formatRecommendedAction(action: string): string {
  return RECOMMENDED_ACTION_LABELS[action] ?? action.replace(/_/g, ' ')
}

export function recommendedActionTone(action: string): ActionBadgeTone {
  if (action === 'auto_apply') return 'auto'
  if (action === 'review_recommended') return 'warning'
  return 'neutral'
}

export function recommendedActionIcon(action: string): LucideIcon {
  if (action === 'auto_apply') return Zap
  if (action === 'review_recommended') return Eye
  return Minus
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`
}

/** ISO-ish, fixed-width - built for a monospace log column, not prose. */
export function formatLogTimestamp(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso

  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

/**
 * Backend reason strings for recommend/auto_apply entries are semicolon-
 * joined clauses (see recommendation.py's _build_reason): the first clause
 * is the human "why", any trailing clauses are the staleness/duplicate/size
 * breakdown. Splitting on that structural delimiter - rather than trying to
 * regex specific field names out of free text - is what lets the Audit Log
 * show a short primary reason with quiet secondary details underneath,
 * without needing a backend schema change.
 */
export function splitReasonDetails(reason: string): { primary: string; details: string[] } {
  const clauses = reason
    .split(/;\s*/)
    .map((c) => c.replace(/\.$/, '').trim())
    .filter(Boolean)

  if (clauses.length === 0) return { primary: reason, details: [] }
  const [primary, ...details] = clauses
  return { primary, details }
}

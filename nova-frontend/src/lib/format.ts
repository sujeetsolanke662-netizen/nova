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

const ACTION_TYPE_LABELS: Record<string, string> = {
  recommend: 'Recommendation',
  guardrail_block: 'Guardrail block',
}

export function formatActionType(actionType: string): string {
  return ACTION_TYPE_LABELS[actionType] ?? actionType.replace(/_/g, ' ')
}

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card'
import { formatBytes, formatClutterCategory } from '@/lib/format'
import type { ClutterFinding } from '@/types/nova'

/**
 * Categories are taxonomy, not a trust signal - so every bar shares one
 * hue. Identity comes from the label text, not color; only
 * magnitude (bar length) is encoded, so a single series needs no legend.
 */
export function ClutterByCategory({ findings }: { findings: ClutterFinding[] }) {
  const totals = new Map<string, { count: number; bytes: number }>()
  for (const f of findings) {
    const current = totals.get(f.category) ?? { count: 0, bytes: 0 }
    current.count += 1
    current.bytes += f.estimated_size_bytes
    totals.set(f.category, current)
  }

  const rows = [...totals.entries()].sort((a, b) => b[1].bytes - a[1].bytes)
  const maxBytes = Math.max(...rows.map(([, v]) => v.bytes), 1)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Clutter by category</CardTitle>
      </CardHeader>
      <CardBody>
        <ul className="space-y-4">
          {rows.map(([category, { count, bytes }]) => (
            <li key={category}>
              <div className="mb-1.5 flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-ink">{formatClutterCategory(category)}</span>
                <span className="shrink-0 font-mono text-xs text-ink-muted">
                  {count} item{count === 1 ? '' : 's'} · {formatBytes(bytes)}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-border-faint">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${Math.max((bytes / maxBytes) * 100, 3)}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  )
}

import { formatBytes, formatPercent } from '@/lib/format'

interface StorageBarProps {
  totalBytes: number
  usedBytes: number
  reclaimableBytes: number
}

const TICKS = [0, 25, 50, 75, 100]

/**
 * The Overview's strongest visual element: a large headline usage figure
 * next to a tick-marked capacity gauge, styled after a system monitor
 * rather than a SaaS progress bar - sharp edges, scale marks, tabular
 * figures. Segments carry visible byte labels since a flat surface doesn't
 * give warn/ok enough contrast to read on color alone.
 */
export function StorageBar({ totalBytes, usedBytes, reclaimableBytes }: StorageBarProps) {
  const safeTotal = totalBytes > 0 ? totalBytes : 1
  const usedPercent = (usedBytes / safeTotal) * 100
  const reclaimable = Math.max(0, Math.min(reclaimableBytes, usedBytes))
  const otherUsed = Math.max(0, usedBytes - reclaimable)
  const free = Math.max(0, totalBytes - usedBytes)

  const pct = (bytes: number) => Math.max((bytes / safeTotal) * 100, bytes > 0 ? 0.4 : 0)

  const segments = [
    { key: 'reclaimable', bytes: reclaimable, className: 'bg-warn' },
    { key: 'used', bytes: otherUsed, className: 'bg-ink-dim' },
    { key: 'free', bytes: free, className: 'bg-ok' },
  ]

  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-4xl font-semibold tabular-nums text-ink">
          {formatPercent(usedPercent)}
        </span>
        <span className="text-xs font-medium tracking-wide text-ink-muted uppercase">
          used of {formatBytes(totalBytes)}
        </span>
      </div>

      <div className="relative mt-3">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-border-faint">
          {segments.map((s, i) => (
            <div
              key={s.key}
              className={s.className}
              style={{ width: `${pct(s.bytes)}%` }}
              title={`${s.key}: ${formatBytes(s.bytes)}`}
            >
              <span
                className={i < segments.length - 1 ? 'block h-full border-r border-bg/70' : 'block h-full'}
              />
            </div>
          ))}
        </div>
        {/* Scale ticks */}
        <div className="relative mt-1 h-3">
          {TICKS.map((t) => (
            <span
              key={t}
              className="absolute -translate-x-1/2 font-mono text-[10px] text-ink-dim"
              style={{ left: `${t}%` }}
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
        <LegendItem swatch="bg-warn" label="Reclaimable" value={formatBytes(reclaimable)} />
        <LegendItem swatch="bg-ink-dim" label="Used" value={formatBytes(otherUsed)} />
        <LegendItem swatch="bg-ok" label="Free" value={formatBytes(free)} />
      </div>
    </div>
  )
}

function LegendItem({ swatch, label, value }: { swatch: string; label: string; value: string }) {
  return (
    <span className="flex items-center gap-1.5 text-ink-muted">
      <span className={`size-2 rounded-full ${swatch}`} aria-hidden="true" />
      {label} <span className="font-mono font-medium text-ink">{value}</span>
    </span>
  )
}

import { formatPercent } from '@/lib/format'

interface CapacityChartProps {
  currentUsedPercent: number
  projectedUsedPercent: number
  daysUntilFull: number | null
}

const WIDTH = 640
const HEIGHT = 220
const PAD_X = 44
const PAD_TOP = 20
const PAD_BOTTOM = 28
const PLOT_H = HEIGHT - PAD_TOP - PAD_BOTTOM

// Chart's own y-domain: 0-100 used%, headroom above the higher of the two
// points so a near-100% projection doesn't collide with the top edge.
const Y_MAX = 100

function yFor(pct: number): number {
  return PAD_TOP + PLOT_H * (1 - Math.min(pct, Y_MAX) / Y_MAX)
}

/**
 * Two real data points - current usage and the linear-trend projection 30
 * days out, exactly what forecast_capacity() returns - connected by a
 * single sequential-hue line, with the 100% capacity ceiling drawn as a
 * fixed reference. Not a fabricated multi-point history: the backend only
 * ever gives us these two numbers, so the chart shows exactly that.
 */
export function CapacityChart({ currentUsedPercent, projectedUsedPercent, daysUntilFull }: CapacityChartProps) {
  const x0 = PAD_X
  const x1 = WIDTH - PAD_X
  const y0 = yFor(currentUsedPercent)
  const y1 = yFor(projectedUsedPercent)
  const yFull = yFor(100)

  const growing = projectedUsedPercent > currentUsedPercent
  const lineColor = growing ? 'var(--color-accent)' : 'var(--color-ok)'

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Projected storage capacity trend">
        {/* Gridlines at 0/25/50/75/100% with axis labels */}
        {[0, 25, 50, 75, 100].map((tick) => (
          <g key={tick}>
            <line
              x1={x0}
              x2={x1}
              y1={yFor(tick)}
              y2={yFor(tick)}
              stroke="var(--color-border-faint)"
              strokeWidth={1}
            />
            <text
              x={x0 - 10}
              y={yFor(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-ink-dim font-mono text-[10px]"
            >
              {tick}%
            </text>
          </g>
        ))}

        {/* 100% capacity ceiling */}
        <line
          x1={x0}
          x2={x1}
          y1={yFull}
          y2={yFull}
          stroke="var(--color-danger)"
          strokeWidth={1.5}
          strokeDasharray="4 4"
          opacity={0.6}
        />

        {/* Trend line */}
        <line x1={x0} x2={x1} y1={y0} y2={y1} stroke={lineColor} strokeWidth={2} strokeLinecap="round" />

        {/* Endpoints */}
        <circle cx={x0} cy={y0} r={4} fill={lineColor} stroke="var(--color-surface)" strokeWidth={2} />
        <circle cx={x1} cy={y1} r={4} fill={lineColor} stroke="var(--color-surface)" strokeWidth={2} />

        {/* Direct labels - only 2 points on this chart, both get one */}
        <text x={x0} y={y0 - 12} textAnchor="start" className="fill-ink font-mono text-[11px] font-semibold">
          {formatPercent(currentUsedPercent)} today
        </text>
        <text x={x1} y={y1 - 12} textAnchor="end" className="fill-ink font-mono text-[11px] font-semibold">
          {formatPercent(projectedUsedPercent)} in 30d
        </text>

        <text x={x0} y={HEIGHT - 8} textAnchor="start" className="fill-ink-dim font-mono text-[10px]">
          Today
        </text>
        <text x={x1} y={HEIGHT - 8} textAnchor="end" className="fill-ink-dim font-mono text-[10px]">
          +30 days
        </text>
      </svg>

      {daysUntilFull !== null && daysUntilFull <= 30 && (
        <p className="mt-1 text-xs text-danger">
          At this rate, capacity is reached in ~{Math.round(daysUntilFull)} days.
        </p>
      )}
    </div>
  )
}

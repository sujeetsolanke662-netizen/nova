import { ChevronDown, ChevronRight } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { formatRecommendedAction, recommendedActionIcon, recommendedActionTone, truncatePath } from '@/lib/format'
import type { RecommendationItem } from '@/types/nova'

interface RecommendationsTableProps {
  items: RecommendationItem[]
  onQuarantine: (path: string, reason: string) => void
  quarantinedPaths: Set<string>
  pendingPath: string | null
}

export function RecommendationsTable({
  items,
  onQuarantine,
  quarantinedPaths,
  pendingPath,
}: RecommendationsTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [reasonDraft, setReasonDraft] = useState<Record<string, string>>({})

  function toggle(path: string) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  function open(path: string) {
    setExpanded((current) => new Set(current).add(path))
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs tracking-wide text-ink-muted uppercase">
            <th className="w-8 py-2.5" />
            <th className="py-2.5 pr-4 font-medium">Path</th>
            <th className="py-2.5 pr-4 font-medium">Action</th>
            <th className="py-2.5 pr-4 text-right font-medium">Staleness</th>
            <th className="py-2.5 pr-4 font-medium">Duplicate of</th>
            <th className="py-2.5 pl-0 font-medium" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-faint">
          {items.map((item) => {
            const isOpen = expanded.has(item.path)
            const alreadyQuarantined = quarantinedPaths.has(item.path)
            const isPending = pendingPath === item.path
            const positiveFactors = item.factors.filter((f) => f.contribution > 0)

            return (
              <Fragment key={item.path}>
                <tr className="cursor-pointer align-top hover:bg-raised" onClick={() => toggle(item.path)}>
                  <td className="py-2 pl-1 text-ink-dim">
                    {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                  </td>
                  <td className="max-w-sm truncate py-2 pr-4 font-mono text-xs text-ink-muted" title={item.path}>
                    {truncatePath(item.path, 60)}
                  </td>
                  <td className="py-2 pr-4">
                    <Badge
                      tone={recommendedActionTone(item.recommended_action)}
                      icon={recommendedActionIcon(item.recommended_action)}
                    >
                      {formatRecommendedAction(item.recommended_action)}
                    </Badge>
                  </td>
                  <td className="py-2 pr-4 text-right font-medium tabular-nums text-ink">
                    {item.staleness_score.toFixed(2)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-ink-muted">
                    {item.duplicate_of
                      ? truncatePath(item.duplicate_of, 32)
                      : item.near_duplicate_of && item.near_duplicate_of.length > 0
                        ? `${item.near_duplicate_of.length} similar`
                        : '—'}
                  </td>
                  <td className="py-2 pl-0 text-right">
                    {item.recommended_action !== 'keep' &&
                      (alreadyQuarantined ? (
                        <Badge tone="brand">Quarantined</Badge>
                      ) : (
                        <Button
                          variant="secondary"
                          onClick={(e) => {
                            e.stopPropagation()
                            open(item.path)
                          }}
                          disabled={isPending}
                        >
                          Quarantine
                        </Button>
                      ))}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-raised">
                    <td />
                    <td colSpan={5} className="space-y-3 py-3 pr-4 text-xs">
                      <ul className="space-y-1">
                        {positiveFactors.length > 0 ? (
                          positiveFactors.map((factor) => (
                            <li key={factor.name} className="text-ink-muted">
                              <span className="font-medium text-ink">{factor.name.replace(/_/g, ' ')}</span>{' '}
                              (+{factor.contribution.toFixed(2)}): {factor.explanation}
                            </li>
                          ))
                        ) : (
                          <li className="text-ink-muted">No contributing factors.</li>
                        )}
                      </ul>

                      {item.near_duplicate_of && item.near_duplicate_of.length > 0 && (
                        <p className="text-ink-muted">
                          Near-duplicate of: {item.near_duplicate_of.map((p) => truncatePath(p, 48)).join(', ')}
                        </p>
                      )}

                      {item.recommended_action !== 'keep' && !alreadyQuarantined && (
                        <form
                          className="flex flex-wrap items-center gap-2"
                          onClick={(e) => e.stopPropagation()}
                          onSubmit={(e) => {
                            e.preventDefault()
                            const reason = reasonDraft[item.path]?.trim()
                            if (!reason) return
                            onQuarantine(item.path, reason)
                          }}
                        >
                          <Input
                            value={reasonDraft[item.path] ?? ''}
                            onChange={(e) =>
                              setReasonDraft((current) => ({ ...current, [item.path]: e.target.value }))
                            }
                            placeholder="Reason for quarantining this file…"
                            className="min-w-[240px] flex-1"
                            aria-label={`Reason to quarantine ${item.path}`}
                          />
                          <Button type="submit" disabled={isPending || !reasonDraft[item.path]?.trim()}>
                            {isPending ? 'Quarantining…' : 'Confirm quarantine'}
                          </Button>
                        </form>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

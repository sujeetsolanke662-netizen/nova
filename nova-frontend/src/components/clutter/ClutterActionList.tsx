import { Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { clutterFindingKey, formatBytes, formatClutterCategoryGroup, truncatePath } from '@/lib/format'
import type { ClutterCategory, ClutterFinding } from '@/types/nova'

const CATEGORY_ORDER: ClutterCategory[] = [
  'orphaned_package',
  'old_kernel',
  'stale_deb_cache',
  'orphaned_config_file',
]

/**
 * Grouped, actionable cleanup list: one heading per category, each finding
 * a row with its own action. safe_to_auto_apply gates the Apply button here
 * too, not just on the backend - see apply_finding()'s UnsafeApplyError,
 * this is the UI's half of that same "no exceptions" rule.
 */
export function ClutterActionList({
  findings,
  onApply,
  pendingKey,
}: {
  findings: ClutterFinding[]
  onApply: (finding: ClutterFinding) => void
  pendingKey: string | null
}) {
  const groups = CATEGORY_ORDER.map((category) => ({
    category,
    items: findings.filter((f) => f.category === category),
  })).filter((group) => group.items.length > 0)

  return (
    <div className="space-y-6">
      {groups.map(({ category, items }) => {
        const totalBytes = items.reduce((sum, f) => sum + f.estimated_size_bytes, 0)
        return (
          <div key={category}>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h3 className="text-sm font-semibold text-ink">{formatClutterCategoryGroup(category)}</h3>
              <span className="font-mono text-xs text-ink-muted">
                {items.length} item{items.length === 1 ? '' : 's'} · {formatBytes(totalBytes)}
              </span>
            </div>
            <ul className="divide-y divide-border-faint rounded-lg border border-border-faint">
              {items.map((finding) => {
                const key = clutterFindingKey(finding)
                const isPending = pendingKey === key
                return (
                  <li key={key} className="flex items-start justify-between gap-4 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-ink">{finding.description}</p>
                      {finding.target_paths.length > 0 && (
                        <p
                          className="mt-0.5 truncate font-mono text-xs text-ink-muted"
                          title={finding.target_paths.join(', ')}
                        >
                          {finding.target_paths.map((p) => truncatePath(p, 56)).join(', ')}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="font-mono text-xs font-medium tabular-nums text-ink-muted">
                        {formatBytes(finding.estimated_size_bytes)}
                      </span>
                      {finding.safe_to_auto_apply ? (
                        <Button
                          variant="secondary"
                          className="px-2.5 py-1.5 text-xs"
                          disabled={isPending}
                          onClick={() => onApply(finding)}
                        >
                          {isPending && <Loader2 className="size-3.5 animate-spin" />}
                          {isPending ? 'Applying…' : 'Apply'}
                        </Button>
                      ) : (
                        <Badge tone="warning">Requires manual review</Badge>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

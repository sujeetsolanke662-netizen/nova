import { ScrollText } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAuditLog } from '@/hooks/useNovaApi'
import { actionTypeIcon, actionTypeTone, formatActionType, formatLogTimestamp, splitReasonDetails } from '@/lib/format'

export function RecentAuditEntries() {
  const { data, isPending, isError, error, refetch } = useAuditLog()
  const recent = data ? [...data].slice(-6).reverse() : []

  return (
    <div className="rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border-faint px-4 py-2.5">
        <p className="text-xs font-semibold tracking-wide text-ink-muted uppercase">Recent activity</p>
        <Link to="/audit-log" className="text-xs font-medium text-accent-ink hover:underline">
          View full log →
        </Link>
      </div>
      <div className="p-4">
        {isPending && <LoadingState label="Loading audit log…" />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : 'Failed to load audit log.'} onRetry={() => refetch()} />
        )}
        {!isPending && !isError && recent.length === 0 && (
          <EmptyState
            icon={ScrollText}
            title="Log is empty"
            description="Entries appear here as NOVA recommends, acts, or blocks something."
          />
        )}
        {!isPending && !isError && recent.length > 0 && (
          <ul className="divide-y divide-border-faint">
            {recent.map((entry) => {
              const { primary } = splitReasonDetails(entry.reason)
              return (
                <li key={entry.entry_id} className="flex items-start gap-3 py-2 first:pt-0 last:pb-0">
                  <span className="mt-0.5 shrink-0 font-mono text-xs text-ink-dim">
                    {formatLogTimestamp(entry.timestamp)}
                  </span>
                  <Badge tone={actionTypeTone(entry.action_type)} icon={actionTypeIcon(entry.action_type)} className="mt-0.5 shrink-0">
                    {formatActionType(entry.action_type)}
                  </Badge>
                  <p className="min-w-0 flex-1 truncate text-sm text-ink" title={primary}>
                    {primary}
                  </p>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

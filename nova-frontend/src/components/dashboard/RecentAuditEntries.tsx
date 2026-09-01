import { Link } from 'react-router-dom'
import { Badge } from '@/components/ui/Badge'
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAuditLog } from '@/hooks/useNovaApi'
import { formatActionType, formatRelativeTime, truncatePath } from '@/lib/format'
import { ScrollText } from 'lucide-react'

export function RecentAuditEntries() {
  const { data, isPending, isError, error, refetch } = useAuditLog()
  const recent = data ? [...data].slice(-5).reverse() : []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent audit activity</CardTitle>
        <Link to="/audit-log" className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400">
          View full log
        </Link>
      </CardHeader>
      <CardBody>
        {isPending && <LoadingState label="Loading audit log…" />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : 'Failed to load audit log.'} onRetry={() => refetch()} />
        )}
        {!isPending && !isError && recent.length === 0 && (
          <EmptyState icon={ScrollText} title="No audit entries yet" description="Entries appear once NOVA records a recommendation or guardrail block." />
        )}
        {!isPending && !isError && recent.length > 0 && (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {recent.map((entry) => (
              <li key={entry.entry_id} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
                <Badge tone={entry.action_type === 'guardrail_block' ? 'danger' : 'brand'} className="mt-0.5 shrink-0">
                  {formatActionType(entry.action_type)}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-slate-700 dark:text-slate-200" title={entry.reason}>
                    {entry.reason}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-xs text-slate-400 dark:text-slate-500">
                    {entry.target_paths.map((p) => truncatePath(p, 40)).join(', ') || '—'}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-slate-400 dark:text-slate-500">
                  {formatRelativeTime(entry.timestamp)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  )
}

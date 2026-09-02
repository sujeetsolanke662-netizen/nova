import { RefreshCw, ScrollText, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { AuditLogTable } from '@/components/audit/AuditLogTable'
import { ChainStatusBanner } from '@/components/audit/ChainStatusBanner'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Select } from '@/components/ui/Select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAuditLog } from '@/hooks/useNovaApi'

type ActionFilter = 'all' | 'recommend' | 'guardrail_block' | 'auto_apply' | 'quarantine' | 'restore'

export function AuditLogPage() {
  const { data, isPending, isError, error, refetch, isFetching } = useAuditLog()
  const [search, setSearch] = useState('')
  const [action, setAction] = useState<ActionFilter>('all')

  const filtered = useMemo(() => {
    if (!data) return []
    const query = search.trim().toLowerCase()

    return [...data]
      .reverse()
      .filter((entry) => {
        if (action !== 'all' && entry.action_type !== action) return false
        if (query) {
          const haystack = `${entry.reason} ${entry.target_paths.join(' ')} ${entry.actor}`.toLowerCase()
          if (!haystack.includes(query)) return false
        }
        return true
      })
  }, [data, search, action])

  return (
    <div>
      <PageHeader
        title="Audit Log"
        description="Every recommendation and guardrail block NOVA has recorded, in a tamper-evident, append-only hash chain."
        actions={
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? 'size-4 animate-spin' : 'size-4'} />
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </Button>
        }
      />

      <div className="mb-4">
        <ChainStatusBanner />
      </div>

      <div className="rounded-lg border border-border">
        <div className="flex flex-wrap items-center gap-3 border-b border-border-faint px-4 py-2.5">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search reason, path, or actor…"
              className="w-full pl-9"
              aria-label="Search audit log"
            />
          </div>
          <Select value={action} onChange={(e) => setAction(e.target.value as ActionFilter)} aria-label="Filter by action type">
            <option value="all">All actions</option>
            <option value="recommend">Recommendations</option>
            <option value="guardrail_block">Guardrail blocks</option>
            <option value="auto_apply">Auto-applied</option>
            <option value="quarantine">Quarantine</option>
            <option value="restore">Restore</option>
          </Select>
        </div>

        <div className="p-4">
          {isPending && <LoadingState label="Loading audit log…" />}
          {isError && (
            <ErrorState message={error instanceof Error ? error.message : 'Failed to load audit log.'} onRetry={() => refetch()} />
          )}
          {!isPending && !isError && filtered.length === 0 && (
            <EmptyState
              icon={ScrollText}
              title={data && data.length > 0 ? 'No entries match' : 'Log is empty'}
              description={
                data && data.length > 0
                  ? 'Try clearing a filter.'
                  : 'Nothing has been recorded yet — entries appear here as NOVA recommends, acts, or blocks.'
              }
            />
          )}
          {!isPending && !isError && filtered.length > 0 && (
            <>
              <p className="mb-3 text-xs text-ink-muted">
                {filtered.length} of {data?.length ?? 0} entries · click a row for hash details
              </p>
              <AuditLogTable entries={filtered} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

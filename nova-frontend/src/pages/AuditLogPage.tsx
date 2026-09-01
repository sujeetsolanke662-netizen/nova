import { RefreshCw, ScrollText, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { AuditLogTable } from '@/components/audit/AuditLogTable'
import { ChainStatusBanner } from '@/components/audit/ChainStatusBanner'
import { Button } from '@/components/ui/Button'
import { Card, CardBody } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Select } from '@/components/ui/Select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAuditLog } from '@/hooks/useNovaApi'

type ActionFilter = 'all' | 'recommend' | 'guardrail_block'

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
        title="Audit log"
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

      <Card>
        <CardBody className="border-b border-slate-200 dark:border-slate-800">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[220px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
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
            </Select>
          </div>
        </CardBody>

        <CardBody>
          {isPending && <LoadingState label="Loading audit log…" />}
          {isError && (
            <ErrorState message={error instanceof Error ? error.message : 'Failed to load audit log.'} onRetry={() => refetch()} />
          )}
          {!isPending && !isError && filtered.length === 0 && (
            <EmptyState
              icon={ScrollText}
              title="No entries match"
              description={data && data.length > 0 ? 'Try clearing a filter.' : 'Nothing has been logged yet.'}
            />
          )}
          {!isPending && !isError && filtered.length > 0 && (
            <>
              <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
                {filtered.length} of {data?.length ?? 0} entries · click a row for hash details
              </p>
              <AuditLogTable entries={filtered} />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

import { FolderSearch, ListChecks, RefreshCw } from 'lucide-react'
import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { RecommendationsTable } from '@/components/recommendations/RecommendationsTable'
import { Button } from '@/components/ui/Button'
import { Card, CardBody } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Select } from '@/components/ui/Select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useQuarantineMutation } from '@/hooks/useQuarantineActions'
import { useRecommendationsQuery } from '@/hooks/useRecommendations'
import { getTrackedLocation, setTrackedLocation } from '@/lib/trackedLocation'
import type { RecommendedAction } from '@/types/nova'

type ActionFilter = 'all' | RecommendedAction

export function RecommendationsPage() {
  const [rootInput, setRootInput] = useState(getTrackedLocation)
  const [committedRoot, setCommittedRoot] = useState('')
  const [search, setSearch] = useState('')
  const [actionFilter, setActionFilter] = useState<ActionFilter>('all')
  const scan = useRecommendationsQuery(committedRoot)
  const quarantine = useQuarantineMutation()
  const [quarantinedPaths, setQuarantinedPaths] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (scan.isSuccess && committedRoot) setTrackedLocation(committedRoot)
  }, [scan.isSuccess, committedRoot])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = rootInput.trim()
    if (trimmed) setCommittedRoot(trimmed)
  }

  function handleQuarantine(path: string, reason: string) {
    quarantine.mutate(
      { path, reason },
      { onSuccess: () => setQuarantinedPaths((current) => new Set(current).add(path)) },
    )
  }

  const recommendations = scan.data?.recommendations ?? []

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return (scan.data?.recommendations ?? []).filter((item) => {
      if (actionFilter !== 'all' && item.recommended_action !== actionFilter) return false
      if (query && !item.path.toLowerCase().includes(query)) return false
      return true
    })
  }, [scan.data, search, actionFilter])

  const autoApplyCount = recommendations.filter((r) => r.recommended_action === 'auto_apply').length
  const reviewCount = recommendations.filter((r) => r.recommended_action === 'review_recommended').length

  return (
    <div>
      <PageHeader
        title="Recommendations"
        description="An intelligent review queue — duplicate, near-duplicate, and stale files worth a look. Nothing is touched on disk until you quarantine it."
      />

      <Card className="mb-4">
        <CardBody>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2.5 sm:flex-row">
            <Input
              value={rootInput}
              onChange={(e) => setRootInput(e.target.value)}
              placeholder="C:\Users\me\Downloads"
              className="flex-1 font-mono"
              aria-label="Root directory to scan"
            />
            <Button type="submit" disabled={scan.isFetching || !rootInput.trim()}>
              {scan.isFetching ? 'Scanning…' : 'Scan'}
            </Button>
            {committedRoot && (
              <Button variant="secondary" onClick={() => scan.refetch()} disabled={scan.isFetching}>
                <RefreshCw className={scan.isFetching ? 'size-3.5 animate-spin' : 'size-3.5'} />
                Rescan
              </Button>
            )}
          </form>
          <p className="mt-2 text-xs text-ink-muted">
            Must be one of NOVA's configured scan roots and not a protected path — the backend rejects
            anything else.
          </p>
        </CardBody>
      </Card>

      {committedRoot && scan.isPending && (
        <Card>
          <CardBody>
            <LoadingState label="Scanning, deduplicating, and scoring files…" />
          </CardBody>
        </Card>
      )}

      {committedRoot && scan.isError && (
        <Card>
          <CardBody>
            <ErrorState
              message={scan.error instanceof Error ? scan.error.message : 'Scan failed.'}
              onRetry={() => scan.refetch()}
            />
          </CardBody>
        </Card>
      )}

      {scan.data && !scan.isPending && !scan.isError && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-surface px-4 py-2.5 text-sm">
            <SummaryStat label="Scanned" value={scan.data.scanned_count} />
            <SummaryStat label="Auto-apply" value={autoApplyCount} tone="text-ok" />
            <SummaryStat label="Review" value={reviewCount} tone="text-warn" />
            <SummaryStat label="Protected" value={scan.data.protected_count} />
            <span className="font-mono text-xs text-ink-dim">{scan.data.skipped_count} skipped/unreadable</span>
          </div>

          <div className="rounded-lg border border-border">
            <div className="flex flex-wrap items-center gap-3 border-b border-border-faint px-4 py-2.5">
              <div className="relative min-w-[220px] flex-1">
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search path…"
                  className="w-full"
                  aria-label="Search recommendations"
                />
              </div>
              <Select
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value as ActionFilter)}
                aria-label="Filter by recommended action"
              >
                <option value="all">All actions</option>
                <option value="auto_apply">Auto-apply</option>
                <option value="review_recommended">Review</option>
                <option value="keep">Keep</option>
              </Select>
            </div>
            <div className="p-4">
              {filtered.length === 0 ? (
                <EmptyState
                  icon={ListChecks}
                  title={recommendations.length > 0 ? 'No findings match' : 'No recommendations'}
                  description={
                    recommendations.length > 0
                      ? 'Try clearing a filter.'
                      : 'This directory is clean — nothing stale, duplicate, or worth reviewing was found.'
                  }
                />
              ) : (
                <>
                  <p className="mb-3 text-xs text-ink-muted">
                    {filtered.length} of {recommendations.length} finding{recommendations.length === 1 ? '' : 's'}
                  </p>
                  <RecommendationsTable
                    items={filtered}
                    onQuarantine={handleQuarantine}
                    quarantinedPaths={quarantinedPaths}
                    pendingPath={quarantine.isPending ? (quarantine.variables?.path ?? null) : null}
                  />
                </>
              )}
            </div>
          </div>
        </>
      )}

      {!committedRoot && (
        <Card>
          <CardBody>
            <EmptyState
              icon={FolderSearch}
              title="No scan yet"
              description="Enter a directory NOVA is configured to scan and press Scan."
            />
          </CardBody>
        </Card>
      )}
    </div>
  )
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className={`font-mono text-sm font-semibold ${tone ?? 'text-ink'}`}>{value}</span>
    </span>
  )
}

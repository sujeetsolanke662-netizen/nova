import { CheckCircle2, PackageSearch, RefreshCw, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { ClutterActionList } from '@/components/clutter/ClutterActionList'
import { ClutterByCategory } from '@/components/clutter/ClutterByCategory'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Select } from '@/components/ui/Select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAptClutterApplyMutation } from '@/hooks/useAptClutterActions'
import { useAptClutterScan } from '@/hooks/useNovaApi'
import { clutterFindingKey, formatBytes, formatClutterCategory } from '@/lib/format'
import type { ClutterCategory, ClutterFinding } from '@/types/nova'

const CATEGORIES: ClutterCategory[] = [
  'stale_deb_cache',
  'orphaned_config_file',
  'old_kernel',
  'orphaned_package',
]

type SortKey = 'size_desc' | 'size_asc'
type SafetyFilter = 'all' | 'safe' | 'review'

export function StorageCleanupPage() {
  const { data, isPending, isError, error, refetch, isFetching } = useAptClutterScan()
  const apply = useAptClutterApplyMutation()

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<'all' | ClutterCategory>('all')
  const [safety, setSafety] = useState<SafetyFilter>('all')
  const [sort, setSort] = useState<SortKey>('size_desc')
  const [confirmation, setConfirmation] = useState<string | null>(null)

  // Auto-dismiss the confirmation banner rather than leaving it stuck until
  // the next apply - same "brief" feedback as a toast, without pulling in a
  // toast library for this one banner.
  useEffect(() => {
    if (!confirmation) return
    const timer = setTimeout(() => setConfirmation(null), 5000)
    return () => clearTimeout(timer)
  }, [confirmation])

  function handleApply(finding: ClutterFinding) {
    apply.mutate(finding, {
      onSuccess: () => setConfirmation(finding.description),
    })
  }

  const filtered = useMemo(() => {
    if (!data) return []

    const query = search.trim().toLowerCase()
    const results = data.filter((f) => {
      if (category !== 'all' && f.category !== category) return false
      if (safety === 'safe' && !f.safe_to_auto_apply) return false
      if (safety === 'review' && f.safe_to_auto_apply) return false
      if (query) {
        const haystack = `${f.description} ${f.target_paths.join(' ')}`.toLowerCase()
        if (!haystack.includes(query)) return false
      }
      return true
    })

    results.sort((a, b) =>
      sort === 'size_desc'
        ? b.estimated_size_bytes - a.estimated_size_bytes
        : a.estimated_size_bytes - b.estimated_size_bytes,
    )
    return results
  }, [data, search, category, safety, sort])

  const totalBytes = filtered.reduce((sum, f) => sum + f.estimated_size_bytes, 0)

  return (
    <div>
      <PageHeader
        title="Cleanup"
        description="apt/dpkg clutter NOVA can see on this machine: orphaned packages, superseded kernels, stale package cache files, and residual config."
        actions={
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? 'size-4 animate-spin' : 'size-4'} />
            {isFetching ? 'Scanning…' : 'Rescan'}
          </Button>
        }
      />

      {confirmation && (
        <div className="mb-4 flex items-start gap-3 rounded-lg border-l-4 border-ok bg-ok-faint px-4 py-3.5">
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-ok" aria-hidden="true" />
          <div>
            <p className="text-sm font-semibold tracking-wide text-ok">APPLIED</p>
            <p className="mt-0.5 text-sm text-ok">{confirmation}</p>
          </div>
        </div>
      )}

      {!isPending && !isError && data && data.length > 0 && (
        <div className="mb-4">
          <ClutterByCategory findings={data} />
        </div>
      )}

      <div className="rounded-lg border border-border">
        <div className="flex flex-wrap items-center gap-3 border-b border-border-faint px-4 py-2.5">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search description or path…"
              className="w-full pl-9"
              aria-label="Search findings"
            />
          </div>
          <Select
            value={category}
            onChange={(e) => setCategory(e.target.value as typeof category)}
            aria-label="Filter by category"
          >
            <option value="all">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {formatClutterCategory(c)}
              </option>
            ))}
          </Select>
          <Select
            value={safety}
            onChange={(e) => setSafety(e.target.value as SafetyFilter)}
            aria-label="Filter by safety"
          >
            <option value="all">All findings</option>
            <option value="safe">Safe to auto-apply</option>
            <option value="review">Needs review</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} aria-label="Sort by size">
            <option value="size_desc">Largest first</option>
            <option value="size_asc">Smallest first</option>
          </Select>
        </div>

        <div className="p-4">
          {isPending && <LoadingState label="Scanning apt/dpkg state…" />}
          {isError && (
            <ErrorState
              message={error instanceof Error ? error.message : 'Scan failed.'}
              onRetry={() => refetch()}
            />
          )}
          {!isPending && !isError && filtered.length === 0 && (
            <EmptyState
              icon={PackageSearch}
              title={data && data.length > 0 ? 'No findings match' : 'No cleanup findings'}
              description={
                data && data.length > 0
                  ? 'Try clearing a filter.'
                  : 'apt/dpkg state is clean on this machine — nothing orphaned, stale, or superseded.'
              }
            />
          )}
          {!isPending && !isError && filtered.length > 0 && (
            <>
              <p className="mb-3 text-xs text-ink-muted">
                {filtered.length} finding{filtered.length === 1 ? '' : 's'} ·{' '}
                <span className="font-mono">{formatBytes(totalBytes)}</span> reclaimable
              </p>
              <ClutterActionList
                findings={filtered}
                onApply={handleApply}
                pendingKey={apply.isPending && apply.variables ? clutterFindingKey(apply.variables) : null}
              />
              {apply.isError && (
                <p className="mt-3 text-xs text-danger">
                  {apply.error instanceof Error ? apply.error.message : 'Failed to apply this finding.'}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

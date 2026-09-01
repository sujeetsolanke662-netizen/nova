import { PackageSearch, RefreshCw, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { ClutterTable } from '@/components/clutter/ClutterTable'
import { Button } from '@/components/ui/Button'
import { Card, CardBody } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { Select } from '@/components/ui/Select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAptClutterScan } from '@/hooks/useNovaApi'
import { formatBytes, formatClutterCategory } from '@/lib/format'
import type { ClutterCategory } from '@/types/nova'

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

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<'all' | ClutterCategory>('all')
  const [safety, setSafety] = useState<SafetyFilter>('all')
  const [sort, setSort] = useState<SortKey>('size_desc')

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
        title="Storage cleanup"
        description="apt/dpkg clutter NOVA can see on this machine: orphaned packages, superseded kernels, stale package cache files, and residual config."
        actions={
          <Button variant="secondary" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={isFetching ? 'size-4 animate-spin' : 'size-4'} />
            {isFetching ? 'Scanning…' : 'Rescan'}
          </Button>
        }
      />

      <Card>
        <CardBody className="border-b border-slate-200 dark:border-slate-800">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative min-w-[220px] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
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
        </CardBody>

        <CardBody>
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
              title="No findings match"
              description={data && data.length > 0 ? 'Try clearing a filter.' : 'apt/dpkg state is clean on this machine.'}
            />
          )}
          {!isPending && !isError && filtered.length > 0 && (
            <>
              <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
                {filtered.length} finding{filtered.length === 1 ? '' : 's'} · {formatBytes(totalBytes)} reclaimable
              </p>
              <ClutterTable findings={filtered} />
            </>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

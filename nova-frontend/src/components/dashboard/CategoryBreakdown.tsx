import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAptClutterScan } from '@/hooks/useNovaApi'
import { formatBytes, formatClutterCategory } from '@/lib/format'
import { PackageSearch } from 'lucide-react'

export function CategoryBreakdown() {
  const { data, isPending, isError, error, refetch } = useAptClutterScan()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Clutter by category</CardTitle>
      </CardHeader>
      <CardBody>
        {isPending && <LoadingState label="Scanning apt/dpkg state…" />}
        {isError && (
          <ErrorState message={error instanceof Error ? error.message : 'Scan failed.'} onRetry={() => refetch()} />
        )}
        {!isPending && !isError && data && data.length === 0 && (
          <EmptyState icon={PackageSearch} title="No clutter found" description="apt/dpkg state is clean." />
        )}
        {!isPending && !isError && data && data.length > 0 && <BreakdownBars findings={data} />}
      </CardBody>
    </Card>
  )
}

function BreakdownBars({ findings }: { findings: { category: string; estimated_size_bytes: number }[] }) {
  const totals = new Map<string, { count: number; bytes: number }>()
  for (const f of findings) {
    const current = totals.get(f.category) ?? { count: 0, bytes: 0 }
    current.count += 1
    current.bytes += f.estimated_size_bytes
    totals.set(f.category, current)
  }

  const rows = [...totals.entries()].sort((a, b) => b[1].bytes - a[1].bytes)
  const maxBytes = Math.max(...rows.map(([, v]) => v.bytes), 1)

  return (
    <ul className="space-y-4">
      {rows.map(([category, { count, bytes }]) => (
        <li key={category}>
          <div className="mb-1.5 flex items-center justify-between text-sm">
            <span className="font-medium text-slate-700 dark:text-slate-200">
              {formatClutterCategory(category)}
            </span>
            <span className="text-slate-500 dark:text-slate-400">
              {count} item{count === 1 ? '' : 's'} · {formatBytes(bytes)}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-500 to-accent-500"
              style={{ width: `${Math.max((bytes / maxBytes) * 100, 3)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

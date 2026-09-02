import { HardDrive, RefreshCw } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { RecentAuditEntries } from '@/components/dashboard/RecentAuditEntries'
import { StorageBar } from '@/components/overview/StorageBar'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardBody } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useAptClutterScan } from '@/hooks/useNovaApi'
import { useForecastQuery } from '@/hooks/useForecast'
import { useRecommendationsQuery } from '@/hooks/useRecommendations'
import { formatBytes } from '@/lib/format'
import { useTrackedLocation } from '@/lib/trackedLocation'

const HEALTH_META: Record<'healthy' | 'watch' | 'critical', { label: string; tone: BadgeTone }> = {
  healthy: { label: 'Healthy', tone: 'success' },
  watch: { label: 'Watch', tone: 'warning' },
  critical: { label: 'Critical', tone: 'danger' },
}

function healthFromUsedPercent(usedPercent: number): keyof typeof HEALTH_META {
  if (usedPercent >= 90) return 'critical'
  if (usedPercent >= 70) return 'watch'
  return 'healthy'
}

export function OverviewPage() {
  const [trackedLocation, setTrackedLocation] = useTrackedLocation()

  if (!trackedLocation) {
    return (
      <div>
        <PageHeader title="Overview" description="A storage command center for one location NOVA is tracking." />
        <TrackLocationPrompt onTrack={setTrackedLocation} />
      </div>
    )
  }

  return (
    <div>
      <PageHeader title="Overview" description="A read-only command center for the location NOVA is currently tracking." />
      <StorageSummary trackedLocation={trackedLocation} onChangeLocation={setTrackedLocation} />
      <div className="mt-4">
        <RecentAuditEntries />
      </div>
    </div>
  )
}

function TrackLocationPrompt({ onTrack }: { onTrack: (path: string) => void }) {
  const [draft, setDraft] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = draft.trim()
    if (trimmed) onTrack(trimmed)
  }

  return (
    <Card>
      <CardBody>
        <div className="flex items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border text-ink-muted">
            <HardDrive className="size-4.5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-ink">No location tracked yet</p>
            <p className="mt-0.5 text-sm text-ink-muted">
              Point NOVA at a directory to see live storage usage, cleanup opportunities, and recent activity for
              it — the same location powers the top bar's storage indicator and pre-fills Forecast and
              Recommendations.
            </p>
            <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-2 sm:flex-row">
              <Input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="C:\Users\me\Downloads"
                className="flex-1 font-mono"
                aria-label="Location to track"
              />
              <Button type="submit" disabled={!draft.trim()}>
                Track location
              </Button>
            </form>
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

function StorageSummary({
  trackedLocation,
  onChangeLocation,
}: {
  trackedLocation: string
  onChangeLocation: (path: string) => void
}) {
  const forecast = useForecastQuery(trackedLocation)
  const recommendations = useRecommendationsQuery(trackedLocation, { enabled: false })
  const clutter = useAptClutterScan()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(trackedLocation)

  const clutterReclaimable = (clutter.data ?? []).reduce((sum, f) => sum + f.estimated_size_bytes, 0)

  const items = recommendations.data?.recommendations
  const staleCount = items?.filter((i) => i.staleness_score >= 0.6).length
  const duplicateCount = items?.filter((i) => i.duplicate_of || (i.near_duplicate_of?.length ?? 0) > 0).length

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = draft.trim()
    if (trimmed) {
      onChangeLocation(trimmed)
      setEditing(false)
    }
  }

  return (
    <div className="rounded-lg border border-border">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-faint px-5 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold tracking-wide text-ink-muted uppercase">Storage capacity</p>
            {forecast.data && (
              <Badge tone={HEALTH_META[healthFromUsedPercent(forecast.data.used_percent)].tone}>
                {HEALTH_META[healthFromUsedPercent(forecast.data.used_percent)].label}
              </Badge>
            )}
          </div>
          {editing ? (
            <form onSubmit={handleSubmit} className="mt-1.5 flex items-center gap-1.5">
              <Input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="h-7 font-mono text-xs"
                aria-label="Change tracked location"
              />
              <Button type="submit" className="h-7 px-2 text-xs">
                Save
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={() => {
                  setEditing(false)
                  setDraft(trackedLocation)
                }}
              >
                Cancel
              </Button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => setEditing(true)}
              title="Click to change"
              className="mt-0.5 truncate font-mono text-xs text-ink-muted hover:text-accent-ink"
            >
              {trackedLocation}
            </button>
          )}
        </div>
        <Button
          variant="secondary"
          onClick={() => forecast.refetch()}
          disabled={forecast.isFetching}
          className="shrink-0"
        >
          <RefreshCw className={forecast.isFetching ? 'size-3.5 animate-spin' : 'size-3.5'} />
          Refresh
        </Button>
      </div>

      <div className="p-5">
        {forecast.isPending && <LoadingState label="Reading disk usage…" />}
        {forecast.isError && (
          <ErrorState
            message={forecast.error instanceof Error ? forecast.error.message : 'Could not read disk usage.'}
            onRetry={() => forecast.refetch()}
          />
        )}
        {forecast.data && (
          <>
            <StorageBar
              totalBytes={forecast.data.total_bytes}
              usedBytes={forecast.data.used_bytes}
              reclaimableBytes={clutterReclaimable}
            />

            {/* Reclaimable gets a dedicated, elevated callout - it's the one
                number on this page that represents an actionable opportunity,
                not just a status readout. */}
            <div className="mt-4 flex items-center justify-between gap-3 rounded-md border-l-4 border-warn bg-warn-faint px-3 py-2.5">
              <div>
                <p className="text-xs font-semibold tracking-wide text-warn uppercase">Reclaimable now</p>
                <p className="mt-0.5 text-xs text-warn">
                  {clutter.isPending
                    ? 'Scanning apt/dpkg state…'
                    : clutter.isError
                      ? 'apt/dpkg cleanup scan unavailable on this machine'
                      : `${clutter.data.length} cleanup finding${clutter.data.length === 1 ? '' : 's'}`}
                </p>
              </div>
              <span className="font-mono text-xl font-semibold text-warn">
                {clutter.isPending ? '…' : clutter.isError ? '—' : formatBytes(clutterReclaimable)}
              </span>
            </div>

            {/* Stale/duplicate counts are secondary signals - quiet, inline,
                no headline treatment. */}
            <p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-muted">
              <span>
                <span className="font-medium text-ink">{staleCount ?? '—'}</span> stale items
              </span>
              <span>
                <span className="font-medium text-ink">{duplicateCount ?? '—'}</span> duplicate items
              </span>
              {!recommendations.data && <span className="text-ink-dim">— scan in Recommendations</span>}
            </p>
          </>
        )}
      </div>
    </div>
  )
}

import { Camera, TrendingUp } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { CapacityChart } from '@/components/forecast/CapacityChart'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/StateViews'
import { useForecastQuery, useForecastSnapshotMutation } from '@/hooks/useForecast'
import { formatBytes, formatPercent } from '@/lib/format'
import { getTrackedLocation, setTrackedLocation } from '@/lib/trackedLocation'

export function ForecastPage() {
  const [pathInput, setPathInput] = useState(getTrackedLocation)
  const [committedPath, setCommittedPath] = useState(getTrackedLocation)
  const forecast = useForecastQuery(committedPath)
  const snapshot = useForecastSnapshotMutation()

  useEffect(() => {
    if (forecast.isSuccess && committedPath) setTrackedLocation(committedPath)
  }, [forecast.isSuccess, committedPath])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = pathInput.trim()
    if (trimmed) setCommittedPath(trimmed)
  }

  function handleSnapshot() {
    if (committedPath) snapshot.mutate(committedPath)
  }

  return (
    <div>
      <PageHeader
        title="Forecast"
        description="Live disk usage plus a linear-trend capacity projection from recorded usage snapshots."
      />

      <Card className="mb-4">
        <CardBody>
          <form onSubmit={handleSubmit} className="flex flex-col gap-2.5 sm:flex-row">
            <Input
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              placeholder="C:\Users\me or /home/user"
              className="flex-1 font-mono"
              aria-label="Path to check disk usage for"
            />
            <Button type="submit" disabled={forecast.isFetching || !pathInput.trim()}>
              {forecast.isFetching ? 'Checking…' : 'Check'}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={handleSnapshot}
              disabled={!committedPath || snapshot.isPending}
            >
              <Camera className={snapshot.isPending ? 'size-3.5 animate-spin' : 'size-3.5'} />
              {snapshot.isPending ? 'Recording…' : 'Record snapshot'}
            </Button>
          </form>
          {snapshot.isError && (
            <p className="mt-2 text-xs text-danger">
              {snapshot.error instanceof Error ? snapshot.error.message : 'Failed to record a snapshot.'}
            </p>
          )}
          {snapshot.isSuccess && (
            <p className="mt-2 text-xs text-ok">
              Snapshot recorded at {new Date(snapshot.data.timestamp).toLocaleString()}.
            </p>
          )}
        </CardBody>
      </Card>

      {!committedPath && (
        <Card>
          <CardBody>
            <EmptyState
              icon={TrendingUp}
              title="No forecast data"
              description="Enter a path above and press Check to read live disk usage."
            />
          </CardBody>
        </Card>
      )}

      {committedPath && forecast.isPending && (
        <Card>
          <CardBody>
            <LoadingState label="Reading disk usage…" />
          </CardBody>
        </Card>
      )}

      {committedPath && forecast.isError && (
        <Card>
          <CardBody>
            <ErrorState
              message={forecast.error instanceof Error ? forecast.error.message : 'Could not read disk usage.'}
              onRetry={() => forecast.refetch()}
            />
          </CardBody>
        </Card>
      )}

      {committedPath && forecast.data && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="size-4 text-ink-dim" />
              Capacity trend
            </CardTitle>
            <span className="font-mono text-xs text-ink-dim">{committedPath}</span>
          </CardHeader>
          <CardBody>
            <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Fact label="Used now" value={formatPercent(forecast.data.used_percent)} />
              <Fact label="Free space" value={formatBytes(forecast.data.free_bytes)} tone="text-ok" />
              {forecast.data.status === 'ok' ? (
                <>
                  <Fact
                    label="Daily growth"
                    value={`${forecast.data.trend_bytes_per_day >= 0 ? '+' : ''}${formatBytes(forecast.data.trend_bytes_per_day)}/day`}
                    tone="text-warn"
                  />
                  <Fact
                    label="Projected full"
                    value={
                      forecast.data.days_until_full !== null
                        ? `~${Math.round(forecast.data.days_until_full)} days`
                        : 'Not projected'
                    }
                    tone="text-danger"
                  />
                </>
              ) : (
                <div className="col-span-2">
                  <p className="text-xs font-medium text-ink-muted">Trend</p>
                  <p className="mt-0.5 text-sm text-ink-muted">
                    {forecast.data.snapshots_available} of {forecast.data.snapshots_needed} snapshots recorded
                  </p>
                </div>
              )}
            </div>

            {forecast.data.status === 'ok' ? (
              <CapacityChart
                currentUsedPercent={forecast.data.current_used_percent}
                projectedUsedPercent={forecast.data.projected_used_percent_in_30_days}
                daysUntilFull={forecast.data.days_until_full}
              />
            ) : (
              <EmptyState
                icon={Camera}
                title="Not enough history for a trend"
                description="Record a few more snapshots (spaced over time) to unlock a capacity projection."
              />
            )}
          </CardBody>
        </Card>
      )}
    </div>
  )
}

function Fact({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <p className="text-xs font-medium text-ink-muted">{label}</p>
      <p className={`mt-0.5 font-mono text-sm font-semibold ${tone ?? 'text-ink'}`}>{value}</p>
    </div>
  )
}

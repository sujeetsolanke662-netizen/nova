import { HardDrive } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useForecastQuery } from '@/hooks/useForecast'
import { cn } from '@/lib/cn'
import { formatBytes } from '@/lib/format'
import { useTrackedLocation } from '@/lib/trackedLocation'

function usageTone(usedPercent: number): { bar: string; text: string } {
  if (usedPercent >= 90) return { bar: 'bg-danger', text: 'text-danger' }
  if (usedPercent >= 70) return { bar: 'bg-warn', text: 'text-warn' }
  return { bar: 'bg-ok', text: 'text-ok' }
}

export function StorageUsageIndicator() {
  const [trackedLocation, setTrackedLocation] = useTrackedLocation()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const { data, isPending, isError } = useForecastQuery(trackedLocation)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = draft.trim()
    if (!trimmed) return
    setTrackedLocation(trimmed)
    setEditing(false)
    setDraft('')
  }

  if (editing) {
    return (
      <>
        <button
          type="button"
          aria-hidden="true"
          tabIndex={-1}
          className="fixed inset-0 z-40 cursor-default"
          onClick={() => setEditing(false)}
        />
        <form
          onSubmit={handleSubmit}
          className="relative z-50 flex items-center gap-1.5"
        >
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Path to track, e.g. C:\Users\me"
            className="h-8 w-56 font-mono text-xs"
            aria-label="Path to track storage for"
          />
          <Button type="submit" className="h-8 px-2.5 text-xs">
            Track
          </Button>
        </form>
      </>
    )
  }

  if (!trackedLocation) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-ink-muted hover:bg-raised"
      >
        <HardDrive className="size-3.5" aria-hidden="true" />
        Track storage
      </button>
    )
  }

  if (isPending) {
    return (
      <div className="hidden items-center gap-2 text-xs text-ink-muted sm:flex">
        <HardDrive className="size-3.5 animate-pulse" aria-hidden="true" />
        Checking storage…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        title={trackedLocation}
        className="hidden items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-ink-muted hover:bg-raised sm:flex"
      >
        <HardDrive className="size-3.5" aria-hidden="true" />
        Storage unavailable
      </button>
    )
  }

  const tone = usageTone(data.used_percent)

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title={`Tracking ${trackedLocation} — click to change`}
      className="hidden items-center gap-2 rounded-md px-2 py-1 hover:bg-raised sm:flex"
    >
      <HardDrive className={cn('size-3.5', tone.text)} aria-hidden="true" />
      <span className="font-mono text-xs font-medium text-ink">
        {formatBytes(data.used_bytes)} <span className="text-ink-muted">/</span> {formatBytes(data.total_bytes)}
      </span>
      <span className="h-1.5 w-16 overflow-hidden rounded-full bg-border-faint">
        <span
          className={cn('block h-full', tone.bar)}
          style={{ width: `${Math.min(data.used_percent, 100)}%` }}
        />
      </span>
    </button>
  )
}

/**
 * The one filesystem location the top bar's storage indicator and the
 * Overview command center track. Persisted client-side only (localStorage) -
 * NOVA's backend has no concept of a "default" path, so this is purely a
 * frontend convenience that Forecast/Recommendations write to on a
 * successful real request and everything else reads back.
 */
import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'nova-tracked-location'
const CHANGE_EVENT = 'nova-tracked-location-change'

export function getTrackedLocation(): string {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(STORAGE_KEY) ?? ''
}

export function setTrackedLocation(path: string): void {
  const trimmed = path.trim()
  if (!trimmed) return
  window.localStorage.setItem(STORAGE_KEY, trimmed)
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

export function useTrackedLocation(): [string, (path: string) => void] {
  const [location, setLocation] = useState(getTrackedLocation)

  useEffect(() => {
    const sync = () => setLocation(getTrackedLocation())
    window.addEventListener(CHANGE_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(CHANGE_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  const update = useCallback((path: string) => setTrackedLocation(path), [])

  return [location, update]
}

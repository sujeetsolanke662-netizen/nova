import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Keyed by "committed" root (set only when the user submits a scan, not on
 * every keystroke) so the result is a normal cached query - which lets the
 * Overview command center passively read the same entry (enabled: false,
 * no fetch of its own) to surface stale/duplicate counts for whatever
 * location was last scanned, without ever triggering a scan itself.
 */
export function useRecommendationsQuery(root: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['recommendations', root],
    queryFn: () => api.recommendations(root),
    enabled: (options?.enabled ?? true) && root.trim().length > 0,
    staleTime: 30_000,
    retry: 1,
  })
}

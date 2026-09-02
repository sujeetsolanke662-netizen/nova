import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

/**
 * Passive, cacheable read of forecast(path) - shared by the top bar's
 * storage indicator, the Overview command center, and ForecastPage itself
 * (keyed by its "committed" path, not the raw input). All three read the
 * same cache entry when they're pointed at the same location, so checking
 * a path once on the Forecast page is enough to light up the top bar too.
 */
export function useForecastQuery(path: string) {
  return useQuery({
    queryKey: ['forecast', path],
    queryFn: () => api.forecast(path),
    enabled: path.trim().length > 0,
    staleTime: 30_000,
    retry: 1,
  })
}

export function useForecastSnapshotMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (path: string) => api.forecastSnapshot(path),
    onSuccess: (_data, path) => {
      queryClient.invalidateQueries({ queryKey: ['forecast', path] })
    },
  })
}

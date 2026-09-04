import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ClutterFinding } from '@/types/nova'

export function useAptClutterApplyMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (finding: ClutterFinding) => api.aptClutterApply(finding),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apt-clutter-scan'] })
      queryClient.invalidateQueries({ queryKey: ['audit-log'] })
      queryClient.invalidateQueries({ queryKey: ['audit-log-verify'] })
    },
  })
}

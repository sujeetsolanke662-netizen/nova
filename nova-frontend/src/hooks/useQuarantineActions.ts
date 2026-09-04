import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useQuarantineMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ path, reason }: { path: string; reason: string }) =>
      api.quarantineFile(path, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quarantine'] })
      queryClient.invalidateQueries({ queryKey: ['audit-log'] })
      queryClient.invalidateQueries({ queryKey: ['audit-log-verify'] })
    },
  })
}

export function useQuarantineRestoreMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (quarantineId: string) => api.quarantineRestore(quarantineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quarantine'] })
      queryClient.invalidateQueries({ queryKey: ['audit-log'] })
      queryClient.invalidateQueries({ queryKey: ['audit-log-verify'] })
    },
  })
}

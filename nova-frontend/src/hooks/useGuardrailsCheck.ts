import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useGuardrailsCheck() {
  return useMutation({
    mutationFn: (path: string) => api.guardrailsCheck(path),
  })
}

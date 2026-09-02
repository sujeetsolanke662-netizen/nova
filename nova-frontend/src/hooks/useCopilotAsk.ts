import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api'

export function useCopilotAsk() {
  return useMutation({
    mutationFn: ({ question, root }: { question: string; root: string }) =>
      api.copilotAsk(question, root),
  })
}

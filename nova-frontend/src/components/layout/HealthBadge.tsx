import { useHealth } from '@/hooks/useNovaApi'
import { cn } from '@/lib/cn'

export function HealthBadge({ compact = false }: { compact?: boolean }) {
  const { data, isPending, isError } = useHealth()

  const ok = !isPending && !isError && data?.status === 'ok'
  const label = isPending ? 'Checking' : ok ? 'Backend connected' : 'Backend unreachable'

  return (
    <div
      className={cn(
        'flex items-center gap-1.5 rounded-md text-xs font-medium text-ink-muted',
        compact ? '' : 'bg-raised px-2.5 py-1',
      )}
    >
      <span
        className={cn(
          'inline-block size-1.5 shrink-0 rounded-full',
          isPending ? 'bg-ink-dim' : ok ? 'bg-ok' : 'bg-danger',
        )}
        aria-hidden="true"
      />
      {label}
    </div>
  )
}

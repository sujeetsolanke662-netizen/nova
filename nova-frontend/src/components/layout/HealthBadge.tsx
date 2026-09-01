import { useHealth } from '@/hooks/useNovaApi'
import { cn } from '@/lib/cn'

export function HealthBadge() {
  const { data, isPending, isError } = useHealth()

  const ok = !isPending && !isError && data?.status === 'ok'
  const label = isPending ? 'Checking…' : ok ? 'Backend online' : 'Backend unreachable'

  return (
    <div className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
      <span className="relative flex size-2">
        {ok && (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        )}
        <span
          className={cn(
            'relative inline-flex size-2 rounded-full',
            isPending ? 'bg-slate-400' : ok ? 'bg-emerald-500' : 'bg-rose-500',
          )}
        />
      </span>
      {label}
    </div>
  )
}

import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Spinner } from '@/components/ui/Spinner'
import { useAuditLogVerify } from '@/hooks/useNovaApi'
import { cn } from '@/lib/cn'

export function ChainStatusBanner() {
  const { data, isPending, isError } = useAuditLogVerify()

  if (isPending) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <Spinner className="size-4" />
        Verifying hash chain…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
        <AlertTriangle className="size-4 shrink-0" />
        Could not verify the audit chain right now.
      </div>
    )
  }

  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-lg border px-4 py-3 text-sm',
        data.valid
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300'
          : 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300',
      )}
    >
      {data.valid ? (
        <>
          <CheckCircle2 className="size-4 shrink-0" />
          Hash chain verified — every entry links to the one before it, unbroken.
        </>
      ) : (
        <>
          <AlertTriangle className="size-4 shrink-0" />
          Chain integrity broken at entry #{data.broken_at_entry}. This log may have been tampered with.
        </>
      )}
    </div>
  )
}

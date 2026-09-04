import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { Spinner } from '@/components/ui/Spinner'
import { useAuditLogVerify } from '@/hooks/useNovaApi'

/**
 * NOVA's core trust signal: the audit trail is a tamper-evident hash chain,
 * and this is where that gets proven, not just asserted. Deliberately
 * heavier than a routine alert - left accent bar, bold verification line,
 * no animation/gradient per the design brief.
 */
export function ChainStatusBanner() {
  const { data, isPending, isError } = useAuditLogVerify()

  if (isPending) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm text-ink-muted">
        <Spinner className="size-3.5" />
        Verifying hash chain…
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2.5 rounded-lg border-l-4 border-warn bg-warn-faint px-4 py-3 text-sm text-warn">
        <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
        Could not verify the audit chain right now.
      </div>
    )
  }

  if (!data.valid) {
    return (
      <div className="flex items-start gap-3 rounded-lg border-l-4 border-danger bg-danger-faint px-4 py-3.5">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-danger" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold tracking-wide text-danger">CHAIN INTEGRITY BROKEN</p>
          <p className="mt-0.5 text-sm text-danger">
            Tampering detected at entry <span className="font-mono">#{data.broken_at_entry}</span>. This log
            can no longer be trusted as an unbroken record.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-start gap-3 rounded-lg border-l-4 border-ok bg-ok-faint px-4 py-3.5">
      <ShieldCheck className="mt-0.5 size-5 shrink-0 text-ok" aria-hidden="true" />
      <div>
        <p className="text-sm font-semibold tracking-wide text-ok">HASH CHAIN VERIFIED</p>
        <p className="mt-0.5 text-sm text-ok">
          Every entry cryptographically links to the one before it — the audit trail is intact and
          verifiable, unbroken.
        </p>
      </div>
    </div>
  )
}

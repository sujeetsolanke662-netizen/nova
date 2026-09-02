import { RotateCcw } from 'lucide-react'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import { cn } from '@/lib/cn'
import { formatLogTimestamp, truncatePath } from '@/lib/format'
import type { QuarantineEntry, QuarantineStatus } from '@/types/nova'

const STATUS_TONE: Record<QuarantineStatus, BadgeTone> = {
  quarantined: 'brand',
  restored: 'success',
  purged: 'neutral',
}

interface QuarantineTableProps {
  entries: QuarantineEntry[]
  onRestore: (quarantineId: string) => void
  pendingId: string | null
}

export function QuarantineTable({ entries, onRestore, pendingId }: QuarantineTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-[11px] font-medium tracking-wide text-ink-muted uppercase">
            <th className="py-2 pr-4">Original path</th>
            <th className="py-2 pr-4">Reason</th>
            <th className="py-2 pr-4">Quarantined at</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2 pl-0" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-faint">
          {entries.map((entry) => {
            const isPending = pendingId === entry.quarantine_id
            return (
              <tr key={entry.quarantine_id} className="align-top">
                <td className="max-w-xs py-2 pr-4 font-mono text-xs text-ink-muted" title={entry.original_path}>
                  {truncatePath(entry.original_path, 48)}
                </td>
                <td className="max-w-sm py-2 pr-4 text-ink">{entry.reason}</td>
                <td className="py-2 pr-4 font-mono text-xs whitespace-nowrap text-ink-muted">
                  {formatLogTimestamp(entry.quarantined_at)}
                </td>
                <td className="py-2 pr-4">
                  <Badge tone={STATUS_TONE[entry.status]}>{entry.status}</Badge>
                </td>
                <td className="py-2 pl-0 text-right">
                  {entry.status === 'quarantined' && (
                    <button
                      type="button"
                      onClick={() => onRestore(entry.quarantine_id)}
                      disabled={isPending}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-md border border-ok/40 px-2.5 py-1 text-xs font-medium text-ok',
                        'hover:bg-ok-faint disabled:cursor-not-allowed disabled:opacity-60',
                      )}
                    >
                      <RotateCcw className={isPending ? 'size-3 animate-spin' : 'size-3'} aria-hidden="true" />
                      {isPending ? 'Restoring…' : 'Restore'}
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

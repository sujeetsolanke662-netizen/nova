import { ChevronDown, ChevronRight } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import {
  actionTypeIcon,
  actionTypeTone,
  formatActionType,
  formatLogTimestamp,
  splitReasonDetails,
  truncatePath,
} from '@/lib/format'
import type { AuditLogEntry } from '@/types/nova'

export function AuditLogTable({ entries }: { entries: AuditLogEntry[] }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  function toggle(id: number) {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-[11px] font-medium tracking-wide text-ink-muted uppercase">
            <th className="w-6 py-2" />
            <th className="py-2 pr-4">Timestamp</th>
            <th className="py-2 pr-4">Action</th>
            <th className="py-2 pr-4">Path</th>
            <th className="py-2 pr-4">Reason</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-faint">
          {entries.map((entry) => {
            const isOpen = expanded.has(entry.entry_id)
            const primaryPath = entry.target_paths[0]
            const isBlocked = entry.action_type === 'guardrail_block'
            const { primary, details } = splitReasonDetails(entry.reason)

            return (
              <Fragment key={entry.entry_id}>
                <tr
                  className="cursor-pointer align-top hover:bg-raised"
                  onClick={() => toggle(entry.entry_id)}
                >
                  <td
                    className={
                      isBlocked
                        ? 'border-l-2 border-l-danger py-2 pl-1 text-ink-dim'
                        : 'py-2 pl-1 text-ink-dim'
                    }
                  >
                    {isOpen ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-ink-muted">
                    {formatLogTimestamp(entry.timestamp)}
                  </td>
                  <td className="py-2 pr-4">
                    <Badge tone={actionTypeTone(entry.action_type)} icon={actionTypeIcon(entry.action_type)}>
                      {formatActionType(entry.action_type)}
                    </Badge>
                  </td>
                  <td className="max-w-[220px] truncate py-2 pr-4 font-mono text-xs text-ink-muted" title={primaryPath}>
                    {primaryPath ? truncatePath(primaryPath, 40) : '—'}
                    {entry.target_paths.length > 1 && (
                      <span className="ml-1 text-ink-dim">+{entry.target_paths.length - 1}</span>
                    )}
                  </td>
                  <td className="max-w-sm py-2 pr-4">
                    <p className="truncate text-ink" title={primary}>
                      {primary}
                    </p>
                    {details.length > 0 && (
                      <p className="truncate text-xs text-ink-dim" title={details.join(' · ')}>
                        {details.join(' · ')}
                      </p>
                    )}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-raised">
                    <td className={isBlocked ? 'border-l-2 border-l-danger' : undefined} />
                    <td colSpan={4} className="py-3 pr-4">
                      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1.5 font-mono text-xs">
                        <DetailRow label="Entry" value={`#${entry.entry_id}`} />
                        <DetailRow label="Actor" value={entry.actor} />
                        <DetailRow
                          label="Target paths"
                          value={entry.target_paths.map((p) => truncatePath(p, 80)).join(', ') || '—'}
                        />
                        <DetailRow label="Entry hash" value={entry.entry_hash} />
                        <DetailRow label="Prev hash" value={entry.prev_hash} />
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-ink-dim uppercase">{label}</dt>
      <dd className="min-w-0 break-all text-ink-muted">{value}</dd>
    </>
  )
}

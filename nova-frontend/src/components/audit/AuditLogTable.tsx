import { ChevronDown, ChevronRight } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import { formatActionType, formatDateTime, truncatePath } from '@/lib/format'
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
      <table className="w-full min-w-[760px] text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800 dark:text-slate-400">
            <th className="w-8 py-2.5" />
            <th className="py-2.5 pr-4 font-medium">Entry</th>
            <th className="py-2.5 pr-4 font-medium">Action</th>
            <th className="py-2.5 pr-4 font-medium">Reason</th>
            <th className="py-2.5 pr-4 font-medium">Timestamp</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {entries.map((entry) => {
            const isOpen = expanded.has(entry.entry_id)
            return (
              <Fragment key={entry.entry_id}>
                <tr
                  className="cursor-pointer align-top hover:bg-slate-50 dark:hover:bg-slate-900/60"
                  onClick={() => toggle(entry.entry_id)}
                >
                  <td className="py-3 pl-1 text-slate-400">
                    {isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                  </td>
                  <td className="py-3 pr-4 font-mono text-xs text-slate-500 dark:text-slate-400">
                    #{entry.entry_id}
                  </td>
                  <td className="py-3 pr-4">
                    <Badge tone={entry.action_type === 'guardrail_block' ? 'danger' : 'brand'}>
                      {formatActionType(entry.action_type)}
                    </Badge>
                  </td>
                  <td className="max-w-md py-3 pr-4 text-slate-700 dark:text-slate-200">{entry.reason}</td>
                  <td className="py-3 pr-4 whitespace-nowrap text-slate-500 dark:text-slate-400">
                    {formatDateTime(entry.timestamp)}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-slate-50 dark:bg-slate-900/60">
                    <td />
                    <td colSpan={4} className="space-y-2 py-3 pr-4 font-mono text-xs text-slate-500 dark:text-slate-400">
                      <DetailRow label="Actor" value={entry.actor} />
                      <DetailRow label="Target paths" value={entry.target_paths.map((p) => truncatePath(p, 72)).join(', ') || '—'} />
                      <DetailRow label="Entry hash" value={entry.entry_hash} />
                      <DetailRow label="Prev hash" value={entry.prev_hash} />
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
    <div className="flex flex-wrap gap-2">
      <span className="text-slate-400 dark:text-slate-500">{label}:</span>
      <span className="break-all text-slate-600 dark:text-slate-300">{value}</span>
    </div>
  )
}

import { CheckCircle2, CircleSlash, ShieldAlert } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import type { GuardrailsCheckResponse } from '@/types/nova'

const CLASSIFICATION_META = {
  protected: {
    label: 'Protected',
    tone: 'danger' as const,
    icon: ShieldAlert,
    summary: 'NOVA will never surface, recommend, or act on this path.',
  },
  reviewable: {
    label: 'Reviewable',
    tone: 'success' as const,
    icon: CheckCircle2,
    summary: 'Inside scan scope and not protected — eligible for review.',
  },
  outside_scan_scope: {
    label: 'Outside scan scope',
    tone: 'neutral' as const,
    icon: CircleSlash,
    summary: "Not protected, but outside NOVA's configured scan roots.",
  },
}

export function ClassificationResult({ result }: { result: GuardrailsCheckResponse }) {
  const meta = CLASSIFICATION_META[result.classification]
  const Icon = meta.icon

  return (
    <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex items-start gap-3">
        <div
          className={
            'flex size-9 shrink-0 items-center justify-center rounded-lg ' +
            (meta.tone === 'danger'
              ? 'bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400'
              : meta.tone === 'success'
                ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400'
                : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400')
          }
        >
          <Icon className="size-5" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={meta.tone}>{meta.label}</Badge>
            <span className="break-all font-mono text-xs text-slate-500 dark:text-slate-400">{result.path}</span>
          </div>
          <p className="mt-2 text-sm text-slate-700 dark:text-slate-200">{meta.summary}</p>
          {result.reason && (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              <span className="font-medium text-slate-600 dark:text-slate-300">Reason: </span>
              {result.reason}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

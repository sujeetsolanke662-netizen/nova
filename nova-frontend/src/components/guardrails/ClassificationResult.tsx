import { CheckCircle2, CircleSlash, ShieldAlert } from 'lucide-react'
import { Badge, type BadgeTone } from '@/components/ui/Badge'
import type { GuardrailsCheckResponse } from '@/types/nova'

const CLASSIFICATION_META = {
  protected: {
    label: 'Blocked',
    severity: 'High',
    tone: 'danger' as BadgeTone,
    icon: ShieldAlert,
    summary: 'NOVA will never surface, recommend, or act on this path.',
  },
  reviewable: {
    label: 'Allowed',
    severity: 'None',
    tone: 'success' as BadgeTone,
    icon: CheckCircle2,
    summary: 'Inside scan scope and not protected — eligible for review.',
  },
  outside_scan_scope: {
    label: 'Out of scope',
    severity: 'Low',
    tone: 'neutral' as BadgeTone,
    icon: CircleSlash,
    summary: "Not protected, but outside NOVA's configured scan roots.",
  },
}

export function ClassificationResult({ result }: { result: GuardrailsCheckResponse }) {
  const meta = CLASSIFICATION_META[result.classification]
  const Icon = meta.icon

  return (
    <div className="rounded-lg border border-border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-faint px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Icon
            className={
              meta.tone === 'danger'
                ? 'size-4 text-danger'
                : meta.tone === 'success'
                  ? 'size-4 text-ok'
                  : 'size-4 text-ink-dim'
            }
            aria-hidden="true"
          />
          <Badge tone={meta.tone}>{meta.label}</Badge>
          <span className="text-xs text-ink-dim">Severity: {meta.severity}</span>
        </div>
        <span className="break-all font-mono text-xs text-ink-muted">{result.path}</span>
      </div>
      <div className="px-4 py-3">
        <p className="text-sm text-ink">{meta.summary}</p>
        {result.reason && (
          <p className="mt-1.5 text-sm text-ink-muted">
            <span className="font-medium text-ink">Reason: </span>
            {result.reason}
          </p>
        )}
      </div>
    </div>
  )
}

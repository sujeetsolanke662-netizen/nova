import type { HTMLAttributes } from 'react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Each tone maps to exactly one meaning app-wide - see lib/format.ts's
 * actionTypeTone()/recommendedActionTone() for the canonical mapping:
 *   neutral  - routine/informational (RECOMMENDATION, KEEP)
 *   brand    - user-invoked action (QUARANTINE)
 *   auto     - the system acted on its own, high confidence (AUTO-APPLIED)
 *   success  - verified / safe / reversible (RESTORE, hash chain intact)
 *   warning  - needs attention, unresolved (REVIEW, stale)
 *   danger   - blocked / destructive (GUARDRAIL BLOCK)
 *   nova     - Ask Nova / AI surfaces only
 *
 * brand and nova share the single accent hue (NOVA's design language keeps
 * one accent, not a second brand color); auto shares the ok/success hue -
 * both collapse to the same token pair below.
 */
export type BadgeTone = 'neutral' | 'brand' | 'auto' | 'success' | 'warning' | 'danger' | 'nova'

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: 'bg-raised text-ink-muted ring-1 ring-inset ring-border',
  brand: 'bg-accent-faint text-accent-ink ring-1 ring-inset ring-accent/30',
  auto: 'bg-ok-faint text-ok ring-1 ring-inset ring-ok/30',
  success: 'bg-ok-faint text-ok ring-1 ring-inset ring-ok/30',
  warning: 'bg-warn-faint text-warn ring-1 ring-inset ring-warn/30',
  danger: 'bg-danger-faint text-danger ring-1 ring-inset ring-danger/30',
  nova: 'bg-accent-faint text-accent-ink ring-1 ring-inset ring-accent/30',
}

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone
  /** Compact system-status chip: uppercase, tighter tracking. Default true. */
  chip?: boolean
  /** Leading glyph so meaning never depends on color alone. */
  icon?: LucideIcon
}

export function Badge({ tone = 'neutral', chip = true, icon: Icon, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded font-mono font-semibold',
        chip ? 'px-1.5 py-0.5 text-[10px] tracking-wide uppercase' : 'px-2 py-0.5 text-xs',
        TONE_CLASSES[tone],
        className,
      )}
      {...props}
    >
      {Icon && <Icon className={chip ? 'size-2.5' : 'size-3'} aria-hidden="true" />}
      {children}
    </span>
  )
}

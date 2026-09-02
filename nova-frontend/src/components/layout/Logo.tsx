export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <div className={className}>
      <div className="flex items-center gap-2.5">
        <img src="/favicon.svg" alt="" className={compact ? 'size-6' : 'size-7'} />
        {compact ? (
          <p className="font-display text-base font-semibold tracking-tight text-ink">NOVA</p>
        ) : (
          <div className="leading-tight">
            <p className="font-display text-base font-semibold tracking-tight text-ink">NOVA</p>
            <p className="text-[11px] text-ink-muted">Storage Intelligence</p>
          </div>
        )}
      </div>
    </div>
  )
}

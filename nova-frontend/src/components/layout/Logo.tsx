export function Logo({ className }: { className?: string }) {
  return (
    <div className={className}>
      <div className="flex items-center gap-2.5">
        <img src="/favicon.svg" alt="" className="size-7" />
        <div className="leading-tight">
          <p className="text-sm font-bold tracking-wide text-slate-900 dark:text-slate-50">NOVA</p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">Storage optimizer</p>
        </div>
      </div>
    </div>
  )
}

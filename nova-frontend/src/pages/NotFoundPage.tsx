import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-raised text-ink-dim">
        <Compass className="size-6" />
      </div>
      <div>
        <h1 className="font-display text-lg font-semibold text-ink">Page not found</h1>
        <p className="mt-1 text-sm text-ink-muted">This page doesn't exist in NOVA's dashboard.</p>
      </div>
      <Link
        to="/"
        className="inline-flex items-center justify-center gap-2 rounded-md bg-accent px-3.5 py-2 text-sm font-medium text-accent-contrast transition-colors hover:brightness-110"
      >
        Back to dashboard
      </Link>
    </div>
  )
}

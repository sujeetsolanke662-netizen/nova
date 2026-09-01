import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500">
        <Compass className="size-6" />
      </div>
      <div>
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-50">Page not found</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          This page doesn't exist in NOVA's dashboard.
        </p>
      </div>
      <Link
        to="/"
        className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-brand-700"
      >
        Back to dashboard
      </Link>
    </div>
  )
}

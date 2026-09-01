import { LayoutDashboard, ScrollText, ShieldCheck, Trash2, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/cn'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/storage-cleanup', label: 'Storage cleanup', icon: Trash2, end: false },
  { to: '/guardrails', label: 'Guardrails', icon: ShieldCheck, end: false },
  { to: '/audit-log', label: 'Audit log', icon: ScrollText, end: false },
] as const

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex h-full flex-col gap-1 p-3" aria-label="Primary">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100',
            )
          }
        >
          <Icon className="size-4.5" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export function MobileSidebarHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
      <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">Menu</span>
      <button
        type="button"
        onClick={onClose}
        className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
        aria-label="Close menu"
      >
        <X className="size-4.5" />
      </button>
    </div>
  )
}

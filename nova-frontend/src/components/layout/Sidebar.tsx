import { X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { HealthBadge } from '@/components/layout/HealthBadge'
import { cn } from '@/lib/cn'
import { NAV_GROUPS } from '@/lib/navigation'

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex h-full flex-col" aria-label="Primary">
      <div className="flex-1 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.heading} className="mb-6 last:mb-0">
            <p className="mb-2 px-3 text-[10px] font-semibold tracking-wider text-ink-muted uppercase">
              {group.heading}
            </p>
            <div className="flex flex-col gap-0.5">
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-raised text-accent-ink'
                        : 'text-ink-muted hover:bg-raised hover:text-ink',
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  {label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-border-faint px-4 py-3">
        <HealthBadge compact />
      </div>
    </nav>
  )
}

export function MobileSidebarHeader({ onClose }: { onClose: () => void }) {
  return (
    <div className="flex items-center justify-between border-b border-border-faint px-4 py-3">
      <span className="text-sm font-semibold text-ink">Menu</span>
      <button
        type="button"
        onClick={onClose}
        className="rounded-md p-1.5 text-ink-muted hover:bg-raised"
        aria-label="Close menu"
      >
        <X className="size-4.5" />
      </button>
    </div>
  )
}

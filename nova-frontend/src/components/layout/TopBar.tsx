import { Menu } from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { HealthBadge } from '@/components/layout/HealthBadge'
import { Logo } from '@/components/layout/Logo'
import { StorageUsageIndicator } from '@/components/layout/StorageUsageIndicator'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { NAV_ITEMS } from '@/lib/navigation'

function useSectionTitle(): string {
  const { pathname } = useLocation()
  const match = NAV_ITEMS.find((item) => (item.end ? pathname === item.to : pathname.startsWith(item.to)))
  return match?.label ?? 'Not found'
}

export function TopBar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const section = useSectionTitle()

  return (
    <header className="sticky top-0 z-30 flex h-11 items-center justify-between gap-4 border-b border-border-faint bg-bg px-4 lg:px-5">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          onClick={onOpenMobileNav}
          className="rounded-md p-1.5 text-ink-muted hover:bg-raised lg:hidden"
          aria-label="Open menu"
        >
          <Menu className="size-5" />
        </button>
        <Logo compact />
        <span className="hidden text-ink-dim sm:inline" aria-hidden="true">
          /
        </span>
        <h1 className="hidden truncate text-sm font-medium text-ink sm:block">{section}</h1>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <StorageUsageIndicator />
        <div className="hidden h-5 w-px bg-border sm:block" aria-hidden="true" />
        <HealthBadge />
        <ThemeToggle />
      </div>
    </header>
  )
}

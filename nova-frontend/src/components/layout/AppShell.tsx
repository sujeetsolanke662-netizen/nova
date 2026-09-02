import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Logo } from '@/components/layout/Logo'
import { MobileSidebarHeader, Sidebar } from '@/components/layout/Sidebar'
import { TopBar } from '@/components/layout/TopBar'

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex h-dvh flex-col bg-bg">
      <TopBar onOpenMobileNav={() => setMobileNavOpen(true)} />

      <div className="flex min-h-0 flex-1">
        {/* Desktop sidebar */}
        <aside className="hidden w-56 shrink-0 lg:block">
          <Sidebar />
        </aside>

        {/* Mobile slide-over sidebar */}
        {mobileNavOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <button
              type="button"
              aria-label="Close menu overlay"
              className="absolute inset-0 bg-black/50"
              onClick={() => setMobileNavOpen(false)}
            />
            <div className="relative flex h-full w-64 flex-col bg-bg">
              <MobileSidebarHeader onClose={() => setMobileNavOpen(false)} />
              <div className="border-b border-border-faint px-4 py-3">
                <Logo />
              </div>
              <div className="flex-1 overflow-y-auto">
                <Sidebar onNavigate={() => setMobileNavOpen(false)} />
              </div>
            </div>
          </div>
        )}

        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-4 py-5 lg:px-8 lg:py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

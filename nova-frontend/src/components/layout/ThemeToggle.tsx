import { Moon, Sun } from 'lucide-react'
import { useTheme } from '@/hooks/useTheme'

export function ThemeToggle() {
  const { theme, toggle } = useTheme()

  return (
    <button
      type="button"
      onClick={toggle}
      className="flex size-8 items-center justify-center rounded-md text-ink-muted hover:bg-raised hover:text-ink"
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      {theme === 'dark' ? <Sun className="size-4.5" /> : <Moon className="size-4.5" />}
    </button>
  )
}

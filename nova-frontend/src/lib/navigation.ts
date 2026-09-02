import {
  Archive,
  Gauge,
  ListChecks,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
} from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: typeof Gauge
  end?: boolean
  /** Ask Nova is the one item that gets the purple AI accent instead of blue. */
  nova?: boolean
}

export interface NavGroup {
  heading: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    heading: 'Overview',
    items: [{ to: '/', label: 'Overview', icon: Gauge, end: true }],
  },
  {
    heading: 'Storage',
    items: [
      { to: '/storage-cleanup', label: 'Cleanup', icon: Trash2 },
      { to: '/recommendations', label: 'Recommendations', icon: ListChecks },
      { to: '/quarantine', label: 'Quarantine', icon: Archive },
    ],
  },
  {
    heading: 'Intelligence',
    items: [
      { to: '/forecast', label: 'Forecast', icon: TrendingUp },
      { to: '/ask-nova', label: 'Ask Nova', icon: Sparkles, nova: true },
    ],
  },
  {
    heading: 'Security',
    items: [
      { to: '/guardrails', label: 'Guardrails', icon: ShieldCheck },
      { to: '/audit-log', label: 'Audit Log', icon: ScrollText },
    ],
  },
]

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

import { CheckCircle2, HardDrive, ShieldAlert, Sparkles } from 'lucide-react'
import { CategoryBreakdown } from '@/components/dashboard/CategoryBreakdown'
import { RecentAuditEntries } from '@/components/dashboard/RecentAuditEntries'
import { PageHeader } from '@/components/ui/PageHeader'
import { StatCard } from '@/components/ui/StatCard'
import { useAptClutterScan, useAuditLogVerify } from '@/hooks/useNovaApi'
import { formatBytes } from '@/lib/format'

export function DashboardPage() {
  const clutterScan = useAptClutterScan()
  const verify = useAuditLogVerify()

  const findings = clutterScan.data ?? []
  const totalReclaimable = findings.reduce((sum, f) => sum + f.estimated_size_bytes, 0)
  const safeToApply = findings.filter((f) => f.safe_to_auto_apply)
  const safeToApplyBytes = safeToApply.reduce((sum, f) => sum + f.estimated_size_bytes, 0)

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="A read-only overview of storage waste NOVA has found on this machine and the integrity of its audit trail."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Reclaimable space"
          value={clutterScan.isPending ? '—' : formatBytes(totalReclaimable)}
          hint={`${findings.length} finding${findings.length === 1 ? '' : 's'} from the last scan`}
          icon={HardDrive}
          tone="brand"
        />
        <StatCard
          label="Safe to auto-apply"
          value={clutterScan.isPending ? '—' : formatBytes(safeToApplyBytes)}
          hint={`${safeToApply.length} of ${findings.length} findings flagged safe`}
          icon={Sparkles}
          tone="accent"
        />
        <StatCard
          label="Audit chain"
          value={verify.isPending ? '—' : verify.data?.valid ? 'Intact' : 'Broken'}
          hint={
            verify.data && !verify.data.valid
              ? `Tampering detected at entry #${verify.data.broken_at_entry}`
              : 'Hash chain verified end-to-end'
          }
          icon={verify.data?.valid === false ? ShieldAlert : CheckCircle2}
          tone={verify.data?.valid === false ? 'danger' : 'success'}
        />
        <StatCard
          label="Findings needing review"
          value={clutterScan.isPending ? '—' : findings.length - safeToApply.length}
          hint="Not marked safe to auto-apply"
          icon={ShieldAlert}
          tone="warning"
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <CategoryBreakdown />
        <RecentAuditEntries />
      </div>
    </div>
  )
}

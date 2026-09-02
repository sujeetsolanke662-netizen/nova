import { CategoryBadge } from '@/components/clutter/CategoryBadge'
import { Badge } from '@/components/ui/Badge'
import { formatBytes, truncatePath } from '@/lib/format'
import type { ClutterFinding } from '@/types/nova'

export function ClutterTable({ findings }: { findings: ClutterFinding[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs tracking-wide text-ink-muted uppercase">
            <th className="py-2.5 pr-4 font-medium">Category</th>
            <th className="py-2.5 pr-4 font-medium">Description</th>
            <th className="py-2.5 pr-4 font-medium">Target</th>
            <th className="py-2.5 pr-4 text-right font-medium">Size</th>
            <th className="py-2.5 pl-0 font-medium">Auto-apply</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-faint">
          {findings.map((finding, i) => (
            <tr key={`${finding.category}-${finding.target_paths[0] ?? i}`} className="align-top">
              <td className="py-2 pr-4">
                <CategoryBadge category={finding.category} />
              </td>
              <td className="max-w-sm py-3 pr-4 text-ink">{finding.description}</td>
              <td className="py-2 pr-4">
                <div className="flex flex-col gap-0.5">
                  {finding.target_paths.map((path) => (
                    <span key={path} title={path} className="font-mono text-xs text-ink-muted">
                      {truncatePath(path, 36)}
                    </span>
                  ))}
                </div>
              </td>
              <td className="py-3 pr-4 text-right font-mono font-medium tabular-nums text-ink">
                {formatBytes(finding.estimated_size_bytes)}
              </td>
              <td className="py-3 pl-0">
                <Badge tone={finding.safe_to_auto_apply ? 'success' : 'warning'}>
                  {finding.safe_to_auto_apply ? 'Safe' : 'Review'}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

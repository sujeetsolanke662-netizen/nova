import { Badge } from '@/components/ui/Badge'
import { formatClutterCategory } from '@/lib/format'
import type { ClutterCategory } from '@/types/nova'

const CATEGORY_TONE: Record<ClutterCategory, 'brand' | 'accent' | 'warning' | 'neutral'> = {
  stale_deb_cache: 'accent',
  orphaned_config_file: 'neutral',
  old_kernel: 'warning',
  orphaned_package: 'brand',
}

export function CategoryBadge({ category }: { category: string }) {
  const tone = CATEGORY_TONE[category as ClutterCategory] ?? 'neutral'
  return <Badge tone={tone}>{formatClutterCategory(category)}</Badge>
}

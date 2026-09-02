import { Badge } from '@/components/ui/Badge'
import { formatClutterCategory } from '@/lib/format'

/**
 * Clutter categories are taxonomy, not a trust/action signal - so unlike
 * the action-type badges elsewhere, every category renders neutral. Color
 * is reserved for things that mean safe/blocked/auto/etc, not for labeling.
 */
export function CategoryBadge({ category }: { category: string }) {
  return <Badge tone="neutral">{formatClutterCategory(category)}</Badge>
}

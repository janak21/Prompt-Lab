import { Badge } from '@/components/ui'
import { categoryLabel, categoryVariant } from './category'

export function CategoryBadge({ category }: { category: string | null | undefined }) {
  return <Badge variant={categoryVariant(category)}>{categoryLabel(category)}</Badge>
}

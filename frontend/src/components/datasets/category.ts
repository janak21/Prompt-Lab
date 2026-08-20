import type { BadgeVariant } from '@/components/ui'

// Consistent, always-labeled colour coding for case categories. Standard
// cases get the accent; adversarial categories are grouped by "flavor" of
// hostility so the eye can quickly tell missing-data cases from injection
// attempts from format abuse, without inventing new decorative colours
// outside the app's semantic palette (DESIGN.md — colour is reserved for
// meaning).
const CATEGORY_VARIANT: Record<string, BadgeVariant> = {
  standard: 'accent',
  empty_input: 'warning',
  missing_field: 'warning',
  ambiguous: 'warning',
  contradictory: 'warning',
  boundary_length: 'neutral',
  wrong_language: 'neutral',
  special_characters: 'neutral',
  prompt_injection: 'danger',
  out_of_domain: 'danger',
  hostile_formatting: 'danger',
}

export function categoryVariant(category: string | null | undefined): BadgeVariant {
  if (!category) return 'neutral'
  return CATEGORY_VARIANT[category] ?? 'neutral'
}

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return 'Uncategorized'
  return category
    .split('_')
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(' ')
}

export const ADVERSARIAL_CATEGORIES = [
  'empty_input',
  'missing_field',
  'ambiguous',
  'contradictory',
  'boundary_length',
  'wrong_language',
  'special_characters',
  'prompt_injection',
  'out_of_domain',
  'hostile_formatting',
] as const

export const ALL_CATEGORY_OPTIONS = ['standard', ...ADVERSARIAL_CATEGORIES]

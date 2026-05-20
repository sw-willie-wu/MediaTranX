import i18n from '@/i18n'

/**
 * Resolve a task_type (e.g. 'video.summary') to its localized display label
 * via the i18n `tasks.types` table; falls back to the raw task_type when the
 * table has no entry.
 *
 * task_type contains '.', which vue-i18n would treat as a nested path — so we
 * read the flat key off the messages object directly (message resolver).
 */
export function getTaskTypeLabel(taskType: string): string {
  const messages = (i18n.global as any).messages.value ?? (i18n.global as any).messages
  const locale = (i18n.global as any).locale.value ?? (i18n.global as any).locale
  const types = messages?.[locale]?.tasks?.types
  return types?.[taskType] || taskType
}

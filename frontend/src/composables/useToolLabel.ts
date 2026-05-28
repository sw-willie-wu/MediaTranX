import { useI18n } from 'vue-i18n'

/**
 * Resolve a tool_id (e.g. "audio.transcribe") to its display label.
 *
 * vue-i18n treats "." as a path separator, so flat keys containing dots
 * can't be accessed via `t('tool_labels.audio.transcribe')`. Use `tm()` to
 * fetch the whole `tool_labels` object and do bracket access instead.
 */
export function useToolLabel() {
  const { tm, rt } = useI18n()

  function toolLabel(toolId: string | undefined | null): string {
    if (!toolId) return ''
    const labels = tm('tool_labels') as Record<string, unknown> | null
    const raw = labels?.[toolId]
    if (raw == null) return toolId
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return rt(raw as any)
    } catch {
      return String(raw)
    }
  }

  return { toolLabel }
}

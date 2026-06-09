/** Codes whose i18n message is generic; for these we append the raw backend
 *  detail so the real cause is visible. Specific codes stay clean. */
const GENERIC_DETAIL_CODES = new Set(['remote_error', 'connection_failed'])

/** Format a task error for display. `item.error` has the form "[code] detail"
 *  (RemoteApiError.__str__). For generic codes we append the stripped+truncated
 *  detail to the translated message. */
export function formatTaskError(
  item: { error_code: string | null; error: string | null },
  t: (key: string) => string,
): string {
  if (item.error_code) {
    const key = `tasks.errors.${item.error_code}`
    const translated = t(key)
    if (translated !== key) {
      if (GENERIC_DETAIL_CODES.has(item.error_code) && item.error) {
        const detail = item.error.replace(/^\[[^\]]+\]\s*/, '').slice(0, 160)
        if (detail) return `${translated} (${detail})`
      }
      return translated
    }
  }
  return item.error ? (item.error.length > 100 ? item.error.slice(0, 100) + '...' : item.error) : ''
}

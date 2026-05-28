/**
 * Tool-result preview helper for ChatMessages.vue.
 *
 * Splits a tool-result JSON blob into `{ status, icon, text }` so the list
 * can render the icon and text in separate spans — letting CSS colour the
 * success / failure icon distinctly. Previously the icon was a `✓`/`✗`
 * prefix glued into a single string that inherited one muted colour,
 * which made the two outcomes visually identical (UX-1).
 */

export interface ToolResultPreview {
  /** `'success'` for ok, `'error'` for cancelled/skipped/error, `'neutral'` when the content isn't JSON at all. */
  status: 'success' | 'error' | 'neutral'
  /** `'✓'`, `'✗'`, or `''` (neutral) — what to render in the coloured icon span. */
  icon: '✓' | '✗' | ''
  /** Short, single-line preview text (≤60 chars). */
  text: string
}

const MAX_LEN = 60

function truncate(s: string): string {
  return s.length <= MAX_LEN ? s : s.slice(0, MAX_LEN)
}

export function toolResultPreview(content: string): ToolResultPreview {
  try {
    const parsed = JSON.parse(content)
    if (parsed && typeof parsed === 'object') {
      const p = parsed as Record<string, unknown>
      if (p.error) {
        return { status: 'error', icon: '✗', text: truncate(String(p.error)) }
      }
      if (p.user_cancelled) {
        return { status: 'error', icon: '✗', text: 'cancelled' }
      }
      if (p.skipped) {
        return { status: 'error', icon: '✗', text: truncate(`skipped: ${p.skipped}`) }
      }
      const keys = Object.keys(parsed as Record<string, unknown>)
      if (keys.length > 0) {
        const firstValue = (parsed as Record<string, unknown>)[keys[0]]
        return { status: 'success', icon: '✓', text: truncate(JSON.stringify(firstValue)) }
      }
      return { status: 'success', icon: '✓', text: 'ok' }
    }
    // Non-object JSON-parseable content (numbers, booleans, null, strings).
    return { status: 'success', icon: '✓', text: truncate(String(parsed)) }
  } catch {
    return { status: 'neutral', icon: '', text: truncate(String(content)) }
  }
}

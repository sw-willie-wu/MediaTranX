/**
 * Relative-time formatting for the agent session list. Returns a localized
 * string via the supplied i18n `t`. (No relative-time helper existed in the
 * codebase; keys live under agent.session.time.*.)
 */
type TFn = (key: string, args?: Record<string, unknown>) => string

export function formatRelativeTime(iso: string, t: TFn, now: Date = new Date()): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const diffSec = Math.max(0, Math.floor((now.getTime() - then) / 1000))
  if (diffSec < 60) return t('agent.session.time.just_now')
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return t('agent.session.time.minutes_ago', { n: diffMin })
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return t('agent.session.time.hours_ago', { n: diffHr })
  const diffDay = Math.floor(diffHr / 24)
  return t('agent.session.time.days_ago', { n: diffDay })
}

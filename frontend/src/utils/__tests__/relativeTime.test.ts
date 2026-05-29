import { describe, it, expect } from 'vitest'
import { formatRelativeTime } from '@/utils/relativeTime'

// fake t: returns "key|argsJSON" so we can assert key + args precisely
const t = (key: string, args?: Record<string, unknown>) =>
  args ? `${key}|${JSON.stringify(args)}` : key

describe('formatRelativeTime', () => {
  const now = new Date('2026-05-29T12:00:00Z')

  it('returns just_now under 60s', () => {
    expect(formatRelativeTime('2026-05-29T11:59:30Z', t, now)).toBe('agent.session.time.just_now')
  })

  it('returns minutes_ago under an hour', () => {
    expect(formatRelativeTime('2026-05-29T11:30:00Z', t, now)).toBe('agent.session.time.minutes_ago|{"n":30}')
  })

  it('returns hours_ago under a day', () => {
    expect(formatRelativeTime('2026-05-29T09:00:00Z', t, now)).toBe('agent.session.time.hours_ago|{"n":3}')
  })

  it('returns days_ago beyond a day', () => {
    expect(formatRelativeTime('2026-05-27T12:00:00Z', t, now)).toBe('agent.session.time.days_ago|{"n":2}')
  })

  it('returns empty string for an invalid date', () => {
    expect(formatRelativeTime('not-a-date', t, now)).toBe('')
  })
})

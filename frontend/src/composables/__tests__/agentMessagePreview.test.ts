/**
 * UX-1: tool-result preview helper used by ChatMessages.vue
 *
 * Splits a tool-result JSON blob into a structured preview the message list
 * can render with separate icon + text spans, so success/failure can be
 * coloured distinctly.  Previously the helper inlined a `✓ `/`✗ ` prefix
 * into a single string and the entire preview span inherited the muted
 * `--text-secondary` colour, making success and failure visually identical.
 */

import { describe, it, expect } from 'vitest'
import { toolResultPreview } from '@/composables/agentMessagePreview'

describe('toolResultPreview', () => {
  it('returns error status for {error: ...}', () => {
    const r = toolResultPreview(JSON.stringify({ error: 'agent.error.invalid_field' }))
    expect(r.status).toBe('error')
    expect(r.icon).toBe('✗')
    expect(r.text).toBe('agent.error.invalid_field')
  })

  it('returns error status for {user_cancelled: true}', () => {
    const r = toolResultPreview(JSON.stringify({ user_cancelled: true }))
    expect(r.status).toBe('error')
    expect(r.icon).toBe('✗')
    expect(r.text).toBe('cancelled')
  })

  it('returns error status for {skipped: ...}', () => {
    const r = toolResultPreview(JSON.stringify({ skipped: 'duplicate' }))
    expect(r.status).toBe('error')
    expect(r.icon).toBe('✗')
    expect(r.text).toBe('skipped: duplicate')
  })

  it('returns success status for generic object payload', () => {
    const r = toolResultPreview(JSON.stringify({ ok: true, task_id: 'abc-123' }))
    expect(r.status).toBe('success')
    expect(r.icon).toBe('✓')
    expect(r.text).toContain('true')
  })

  it('returns success status for empty object', () => {
    const r = toolResultPreview('{}')
    expect(r.status).toBe('success')
    expect(r.icon).toBe('✓')
    expect(r.text).toBe('ok')
  })

  it('returns success status for non-object JSON-parseable content', () => {
    const r = toolResultPreview('42')
    expect(r.status).toBe('success')
    expect(r.icon).toBe('✓')
    expect(r.text).toBe('42')
  })

  it('returns neutral status for unparseable content (no icon)', () => {
    const r = toolResultPreview('this is plain text')
    expect(r.status).toBe('neutral')
    expect(r.icon).toBe('')
    expect(r.text).toBe('this is plain text')
  })

  it('truncates long text payloads', () => {
    const long = 'x'.repeat(200)
    const r = toolResultPreview(long)
    expect(r.text.length).toBeLessThanOrEqual(60)
  })
})

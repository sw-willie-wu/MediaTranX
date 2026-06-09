import { describe, it, expect } from 'vitest'
import { formatTaskError } from '../taskError'

const t = (k: string): string => {
  const m: Record<string, string> = {
    'tasks.errors.remote_error': '遠端 API 錯誤。',
    'tasks.errors.connection_failed': '無法連線至遠端伺服器，請檢查連線位址。',
    'tasks.errors.auth_failed': 'API 金鑰無效或已過期。',
  }
  return m[k] ?? k
}

describe('formatTaskError', () => {
  it('appends detail for generic remote_error', () => {
    const out = formatTaskError({ error_code: 'remote_error', error: '[remote_error] Ollama 405: Method Not Allowed' }, t)
    expect(out).toContain('遠端 API 錯誤。')
    expect(out).toContain('Ollama 405: Method Not Allowed')
  })

  it('appends detail for connection_failed', () => {
    const out = formatTaskError({ error_code: 'connection_failed', error: '[connection_failed] Ollama: read timed out' }, t)
    expect(out).toContain('read timed out')
  })

  it('keeps a specific code clean (no detail)', () => {
    const out = formatTaskError({ error_code: 'auth_failed', error: '[auth_failed] bad key' }, t)
    expect(out).toBe('API 金鑰無效或已過期。')
  })

  it('falls back to truncated raw error when code has no i18n', () => {
    const out = formatTaskError({ error_code: 'weird', error: 'something broke' }, t)
    expect(out).toBe('something broke')
  })
})

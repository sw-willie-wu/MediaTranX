import { describe, it, expect } from 'vitest'
import { resolvePastedUrl } from '@/composables/usePasteUpload'

function evt(text: string, files: File[] = []): ClipboardEvent {
  return {
    clipboardData: {
      files,
      getData: (t: string) => (t === 'text/plain' ? text : ''),
    },
  } as unknown as ClipboardEvent
}

const opts = { expanded: false, activeElement: null }

describe('resolvePastedUrl', () => {
  it('returns an http(s) URL', () => {
    expect(resolvePastedUrl(evt('https://youtu.be/abc'), opts)).toBe('https://youtu.be/abc')
    expect(resolvePastedUrl(evt('http://x.com/v'), opts)).toBe('http://x.com/v')
  })

  it('ignores non-URL text', () => {
    expect(resolvePastedUrl(evt('just some words'), opts)).toBeNull()
    expect(resolvePastedUrl(evt('ftp://x'), opts)).toBeNull()
  })

  it('ignores when files are present (files take precedence)', () => {
    const f = new File(['x'], 'a.png', { type: 'image/png' })
    expect(resolvePastedUrl(evt('https://x.com', [f]), opts)).toBeNull()
  })

  it('ignores when the chat panel is expanded', () => {
    expect(resolvePastedUrl(evt('https://x.com'), { expanded: true, activeElement: null })).toBeNull()
  })

  it('trims surrounding whitespace', () => {
    expect(resolvePastedUrl(evt('  https://x.com/v  '), opts)).toBe('https://x.com/v')
  })
})

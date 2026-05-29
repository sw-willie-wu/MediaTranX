import { describe, it, expect, beforeEach } from 'vitest'
import {
  mimeToExt,
  pastedImageName,
  isEditableTarget,
  extractClipboardFiles,
  resolvePaste,
} from '@/composables/usePasteUpload'
import { bubbleExpanded } from '@/composables/useBubbleVisibility'

/** Minimal ClipboardEvent-shaped mock (jsdom's is incomplete). */
function clipboardEvent(opts: {
  files?: File[]
  items?: Array<{ kind: string; type: string; file?: File }>
}): ClipboardEvent {
  const items = (opts.items ?? []).map((i) => ({
    kind: i.kind,
    type: i.type,
    getAsFile: () => i.file ?? null,
  }))
  return {
    clipboardData: {
      files: opts.files ?? [],
      items,
    },
  } as unknown as ClipboardEvent
}

describe('mimeToExt', () => {
  it('maps known image mimes', () => {
    expect(mimeToExt('image/png')).toBe('png')
    expect(mimeToExt('image/jpeg')).toBe('jpg')
    expect(mimeToExt('image/webp')).toBe('webp')
    expect(mimeToExt('image/bmp')).toBe('bmp')
    expect(mimeToExt('image/gif')).toBe('gif')
  })
  it('defaults to png for unknown mime', () => {
    expect(mimeToExt('image/tiff')).toBe('png')
    expect(mimeToExt('')).toBe('png')
  })
})

describe('pastedImageName', () => {
  it('formats pasted-image-YYYYMMDD-HHmmss.ext', () => {
    const d = new Date(2026, 4, 29, 9, 8, 7) // 2026-05-29 09:08:07
    expect(pastedImageName('image/png', d)).toBe('pasted-image-20260529-090807.png')
    expect(pastedImageName('image/jpeg', d)).toBe('pasted-image-20260529-090807.jpg')
  })
})

describe('isEditableTarget', () => {
  it('true for INPUT / TEXTAREA / SELECT', () => {
    expect(isEditableTarget({ tagName: 'INPUT' } as Element)).toBe(true)
    expect(isEditableTarget({ tagName: 'TEXTAREA' } as Element)).toBe(true)
    expect(isEditableTarget({ tagName: 'SELECT' } as Element)).toBe(true)
  })
  it('true for contenteditable (isContentEditable property)', () => {
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: true } as unknown as Element)).toBe(true)
  })
  it('false for null / non-editable', () => {
    expect(isEditableTarget(null)).toBe(false)
    expect(isEditableTarget({ tagName: 'DIV', isContentEditable: false } as unknown as Element)).toBe(false)
  })
})

describe('extractClipboardFiles', () => {
  it('prefers clipboardData.files when present, returning them UNRENAMED (incl. images)', () => {
    const a = new File(['a'], 'a.mp4', { type: 'video/mp4' })
    const b = new File(['b'], 'real-photo.png', { type: 'image/png' }) // image via files branch → keep real name
    const out = extractClipboardFiles(clipboardEvent({ files: [a, b] }))
    expect(out).toEqual([a, b])
    expect(out[1].name).toBe('real-photo.png') // NOT renamed to pasted-image-*
  })
  it('extracts image blobs from items and renames them', () => {
    const blob = new File(['x'], 'clip', { type: 'image/png' })
    const out = extractClipboardFiles(clipboardEvent({ items: [{ kind: 'file', type: 'image/png', file: blob }] }))
    expect(out).toHaveLength(1)
    expect(out[0].type).toBe('image/png')
    expect(out[0].name).toMatch(/^pasted-image-\d{8}-\d{6}\.png$/)
  })
  it('ignores non-file items (e.g. text)', () => {
    const out = extractClipboardFiles(clipboardEvent({ items: [{ kind: 'string', type: 'text/plain' }] }))
    expect(out).toEqual([])
  })
  it('returns empty when nothing present', () => {
    expect(extractClipboardFiles(clipboardEvent({}))).toEqual([])
  })
})

describe('resolvePaste — guards', () => {
  beforeEach(() => { bubbleExpanded.value = false })

  it('returns files for a valid image paste', () => {
    const blob = new File(['x'], 'clip', { type: 'image/png' })
    const e = clipboardEvent({ items: [{ kind: 'file', type: 'image/png', file: blob }] })
    const out = resolvePaste(e, { expanded: false, activeElement: null })
    expect(out).toHaveLength(1)
  })
  it('null when chat panel expanded', () => {
    const blob = new File(['x'], 'clip', { type: 'image/png' })
    const e = clipboardEvent({ items: [{ kind: 'file', type: 'image/png', file: blob }] })
    expect(resolvePaste(e, { expanded: true, activeElement: null })).toBeNull()
  })
  it('null when focus is in an editable element', () => {
    const blob = new File(['x'], 'clip', { type: 'image/png' })
    const e = clipboardEvent({ items: [{ kind: 'file', type: 'image/png', file: blob }] })
    expect(resolvePaste(e, { expanded: false, activeElement: { tagName: 'TEXTAREA' } as Element })).toBeNull()
  })
  it('null for text-only paste (no files)', () => {
    const e = clipboardEvent({ items: [{ kind: 'string', type: 'text/plain' }] })
    expect(resolvePaste(e, { expanded: false, activeElement: null })).toBeNull()
  })
})

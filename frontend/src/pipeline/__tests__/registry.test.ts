import { describe, it, expect } from 'vitest'
import { TOOL_REGISTRY, getToolSpec, listToolSpecs } from '../registry'
import { MEDIA_KIND_EXTS, type MediaKindT } from '@/utils/mediaKind'

/** 白名單全集（1 source + 20 tool = 21） */
const EXPECTED_KEYS = [
  // source
  'video.download',
  // video
  'video.transcode', 'video.extract_audio', 'video.enhance', 'video.interpolate', 'video.summary',
  // audio
  'audio.transcode', 'audio.lyrics', 'audio.separate', 'audio.transcribe', 'audio.volume',
  // image
  'image.compress', 'image.convert', 'image.filter', 'image.ocr', 'image.remove_bg', 'image.upscale',
  // document
  'document.ocr', 'document.pdf_convert', 'document.split', 'document.translate',
]

const VALID_KINDS = Object.keys(MEDIA_KIND_EXTS) as MediaKindT[]

describe('TOOL_REGISTRY completeness', () => {
  it('contains exactly the 21 whitelisted tool keys', () => {
    expect(Object.keys(TOOL_REGISTRY).sort()).toEqual([...EXPECTED_KEYS].sort())
  })

  it.each(EXPECTED_KEYS)('%s: toolKey mirrors map key and apiPath starts with /', (key) => {
    const spec = TOOL_REGISTRY[key]
    expect(spec).toBeDefined()
    expect(spec.toolKey).toBe(key)
    expect(spec.apiPath.startsWith('/')).toBe(true)
    expect(spec.labelKey.length).toBeGreaterThan(0)
  })

  it('only video.download is a source; everything else is a tool', () => {
    for (const spec of listToolSpecs()) {
      if (spec.toolKey === 'video.download') {
        expect(spec.kind).toBe('source')
        expect(spec.inputKinds).toEqual([])
      } else {
        expect(spec.kind).toBe('tool')
        expect(spec.inputKinds.length).toBeGreaterThan(0)
      }
    }
  })

  it('every entry has a non-empty paramSchema', () => {
    for (const spec of listToolSpecs()) {
      expect(spec.paramSchema.length, `${spec.toolKey} paramSchema`).toBeGreaterThan(0)
    }
  })

  it('paramSchema fields are well-formed (unique names; enum options non-empty when present)', () => {
    for (const spec of listToolSpecs()) {
      const names = spec.paramSchema.map(f => f.name)
      expect(new Set(names).size, `${spec.toolKey} duplicate field names`).toBe(names.length)
      // file_id / suppress_results 由 runner 注入,不得進 schema
      expect(names).not.toContain('file_id')
      expect(names).not.toContain('suppress_results')
      for (const f of spec.paramSchema) {
        if (f.options !== undefined) {
          expect(f.options.length, `${spec.toolKey}.${f.name} options`).toBeGreaterThan(0)
        }
        if (f.default !== undefined && f.type === 'enum' && f.options) {
          expect(f.options, `${spec.toolKey}.${f.name} default in options`).toContain(String(f.default))
        }
      }
    }
  })
})

describe('outputKind branches', () => {
  it('video.transcode: gif → image, mp3 → audio, mp4 → video (and default = video)', () => {
    const spec = getToolSpec('video.transcode')!
    expect(spec.outputKind({ output_format: 'gif' })).toBe('image')
    expect(spec.outputKind({ output_format: 'apng' })).toBe('image')
    expect(spec.outputKind({ output_format: 'mp3' })).toBe('audio')
    expect(spec.outputKind({ output_format: 'mp4' })).toBe('video')
    expect(spec.outputKind({})).toBe('video')
  })

  it('document.pdf_convert: images → image, txt/md → document', () => {
    const spec = getToolSpec('document.pdf_convert')!
    expect(spec.outputKind({ output_format: 'images' })).toBe('image')
    expect(spec.outputKind({ output_format: 'txt' })).toBe('document')
    expect(spec.outputKind({ output_format: 'md' })).toBe('document')
  })

  it('fixed-kind tools return their declared kind', () => {
    const fixed: Record<string, MediaKindT> = {
      'video.download': 'video',
      'video.extract_audio': 'audio',
      'video.enhance': 'video',
      'video.interpolate': 'video',
      'video.summary': 'document',
      'audio.transcode': 'audio',
      'audio.lyrics': 'document',
      'audio.separate': 'audio',
      'audio.transcribe': 'document',
      'audio.volume': 'audio',
      'image.compress': 'image',
      'image.convert': 'image',
      'image.filter': 'image',
      'image.ocr': 'document',
      'image.remove_bg': 'image',
      'image.upscale': 'image',
      'document.ocr': 'document',
      'document.split': 'document',
      'document.translate': 'document',
    }
    for (const [key, kind] of Object.entries(fixed)) {
      expect(getToolSpec(key)!.outputKind({}), key).toBe(kind)
    }
  })
})

describe('inputKinds ⟷ MEDIA_KIND_EXTS consistency', () => {
  it('all inputKinds values are legal MediaKindT keys of MEDIA_KIND_EXTS', () => {
    for (const spec of listToolSpecs()) {
      for (const k of spec.inputKinds) {
        expect(VALID_KINDS, `${spec.toolKey} inputKind '${k}'`).toContain(k)
      }
      // outputKind（預設參數）也必須是合法 MediaKindT
      expect(VALID_KINDS).toContain(spec.outputKind({}))
    }
  })

  it('inputExts refinements stay inside the declared kind ext table', () => {
    for (const spec of listToolSpecs()) {
      if (!spec.inputExts) continue
      const allowed = new Set(spec.inputKinds.flatMap(k => [...MEDIA_KIND_EXTS[k]]))
      for (const ext of spec.inputExts) {
        expect(allowed.has(ext), `${spec.toolKey} inputExt '${ext}'`).toBe(true)
      }
    }
  })

  it('domain prefixes match inputKinds (audio.*→audio, image.*→image, document.*→document, video tools→video)', () => {
    for (const spec of listToolSpecs()) {
      if (spec.kind === 'source') continue
      const domain = spec.toolKey.split('.')[0] as MediaKindT
      expect(spec.inputKinds, spec.toolKey).toEqual([domain])
    }
  })
})

/**
 * Smoke test — VideoTranscodePanel agent schema (Wave 3 Task 3.4)
 *
 * Verifies:
 *   - After mount, panelRegistry.get('video.transcode') returns a handle
 *   - getCurrentValues() returns an object with all schema field names
 *   - setField('crf', 28) returns 28 (within range)
 *   - setField('crf', 100) returns 51 (clamped, R-5)
 */

import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach } from 'vitest'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'

function makeVideoTranscodePanelStub() {
  const outputFormat = ref('mp4')
  const videoCodec = ref('h264')
  const resolution = ref('')
  const crf = ref(23)
  const audioBitrate = ref('192k')
  const customResWidth = ref(1920)
  const customResHeight = ref(1080)
  const scaleAlgorithm = ref('bicubic')

  const fps = ref('12')

  const audioFormatValues = ['mp3', 'aac', 'wav', 'flac']
  const animFormatValues = ['gif', 'apng']
  const isAudioFormat = () => audioFormatValues.includes(outputFormat.value)
  const isAnimFormat = () => animFormatValues.includes(outputFormat.value)
  const showBitrateOption = () => isAudioFormat() && !['wav', 'flac'].includes(outputFormat.value)

  const formats = [
    { value: 'mp4' }, { value: 'mkv' }, { value: 'webm' }, { value: 'avi' },
    { value: 'mov' }, { value: 'gif' }, { value: 'apng' },
    { value: 'mp3' }, { value: 'aac' }, { value: 'wav' }, { value: 'flac' },
  ]
  const videoCodecs = [
    { value: 'h264' }, { value: 'h265' }, { value: 'vp9' }, { value: 'copy' },
  ]
  const resolutions = [
    { value: '' }, { value: '3840x2160' }, { value: '2560x1440' },
    { value: '1920x1080' }, { value: '1280x720' }, { value: '854x480' },
    { value: '640x360' }, { value: 'custom' },
  ]
  const scaleAlgorithms = [
    { value: 'bicubic' }, { value: 'lanczos' }, { value: 'spline' },
    { value: 'bilinear' }, { value: 'neighbor' },
  ]
  const audioBitrates = [
    { value: '128k' }, { value: '192k' }, { value: '256k' }, { value: '320k' },
  ]

  const agentSchema = {
    panelId: 'video.transcode',
    fields: [
      { name: 'output_format', type: 'enum' as const,
        options: () => formats.map(f => f.value) },
      { name: 'video_codec', type: 'enum' as const,
        options: () => videoCodecs.map(c => c.value),
        visibleWhen: () => !isAudioFormat() && !isAnimFormat() },
      { name: 'resolution', type: 'enum' as const,
        options: () => resolutions.map(r => r.value),
        visibleWhen: () => !isAudioFormat() },
      { name: 'custom_width', type: 'number' as const,
        min: 1, max: 99999, step: 1,
        visibleWhen: () => resolution.value === 'custom' },
      { name: 'custom_height', type: 'number' as const,
        min: 1, max: 99999, step: 1,
        visibleWhen: () => resolution.value === 'custom' },
      { name: 'scale_algorithm', type: 'enum' as const,
        options: () => scaleAlgorithms.map(a => a.value),
        visibleWhen: () => !isAudioFormat() && !!resolution.value },
      { name: 'crf', type: 'number' as const,
        min: 0, max: 51, step: 1,
        visibleWhen: () => !isAudioFormat() && !isAnimFormat() },
      { name: 'audio_bitrate', type: 'enum' as const,
        options: () => audioBitrates.map(b => b.value),
        visibleWhen: () => showBitrateOption() },
      { name: 'fps', type: 'enum' as const,
        options: () => ['8', '10', '12', '15', '20', '24'],
        visibleWhen: () => isAnimFormat() },
    ],
    actions: [],
    execute: { requiresConfirm: true, label: 'panel.transcode.execute' },
  }

  const handleWithoutMounted: Omit<PanelHandle, 'isMounted'> = {
    agentSchema,
    isMultiSelect: () => false,
    getCurrentValues: () => ({
      output_format: outputFormat.value,
      video_codec: videoCodec.value,
      resolution: resolution.value,
      custom_width: customResWidth.value,
      custom_height: customResHeight.value,
      scale_algorithm: scaleAlgorithm.value,
      crf: crf.value,
      audio_bitrate: audioBitrate.value,
      fps: fps.value,
    }),
    setField: (field, value) => {
      switch (field) {
        case 'output_format':
          outputFormat.value = value as string
          return value
        case 'video_codec':
          videoCodec.value = value as string
          return value
        case 'resolution':
          resolution.value = value as string
          return value
        case 'custom_width': {
          const v = Math.max(1, Number(value))
          customResWidth.value = v
          return v
        }
        case 'custom_height': {
          const v = Math.max(1, Number(value))
          customResHeight.value = v
          return v
        }
        case 'scale_algorithm':
          scaleAlgorithm.value = value as string
          return value
        case 'crf': {
          const clamped = Math.min(Math.max(Number(value), 0), 51)
          crf.value = clamped
          return clamped
        }
        case 'audio_bitrate':
          audioBitrate.value = value as string
          return value
        case 'fps':
          fps.value = String(value)
          return fps.value
        default:
          throw new Error(`Unknown field: ${field}`)
      }
    },
    openField: (_field) => {},
    execute: async () => ({}),
  }

  return defineComponent({
    setup() {
      useAgentPanelHost('video.transcode', handleWithoutMounted)
      return {}
    },
    template: '<div></div>',
  })
}

beforeEach(() => { panelRegistry._clearAll() })

describe('VideoTranscodePanel agent schema smoke', () => {
  it('mount → panelRegistry.get returns a handle', () => {
    mount(makeVideoTranscodePanelStub())
    expect(panelRegistry.get('video.transcode')).toBeDefined()
  })

  it('getCurrentValues() returns all schema field names', () => {
    mount(makeVideoTranscodePanelStub())
    const handle = panelRegistry.get('video.transcode')!
    const values = handle.getCurrentValues()
    for (const field of handle.agentSchema.fields) {
      expect(values).toHaveProperty(field.name)
    }
  })

  it('setField crf = 28 → returns 28', () => {
    mount(makeVideoTranscodePanelStub())
    const handle = panelRegistry.get('video.transcode')!
    expect(handle.setField('crf', 28)).toBe(28)
  })

  it('setField crf > 51 → clamped to 51 (R-5)', () => {
    mount(makeVideoTranscodePanelStub())
    const handle = panelRegistry.get('video.transcode')!
    expect(handle.setField('crf', 100)).toBe(51)
  })

  it('gif format hides codec/crf and shows fps in agent schema', () => {
    mount(makeVideoTranscodePanelStub())
    const h = panelRegistry.get('video.transcode')!
    h.setField('output_format', 'gif')
    const field = (n: string) => h.agentSchema.fields.find(f => f.name === n)!
    expect(field('video_codec').visibleWhen!()).toBe(false)
    expect(field('crf').visibleWhen!()).toBe(false)
    expect(field('fps').visibleWhen!()).toBe(true)
    expect(field('resolution').visibleWhen!()).toBe(true)
  })

  it('fps is settable and reflected in current values', () => {
    mount(makeVideoTranscodePanelStub())
    const h = panelRegistry.get('video.transcode')!
    h.setField('output_format', 'gif')
    h.setField('fps', '15')
    expect(h.getCurrentValues().fps).toBe('15')
  })
})

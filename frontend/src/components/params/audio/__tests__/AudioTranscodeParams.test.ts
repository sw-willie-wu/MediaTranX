/**
 * AudioTranscodeParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.1）。
 * 覆蓋：格式切換 emit、無損隱藏 bitrate、bitrate 動態上限、sample_rate/channels 新 UI、
 * wma 不入選單（schema 有、UI 過濾）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import AudioTranscodeParams from '../AudioTranscodeParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import { hasParamComponent, METAS } from '../../index'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(AudioTranscodeParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

/** AppSelect 依標籤（label 開頭）反查對應實例（同頁多個 AppSelect） */
function findSelectByModelValue(w: ReturnType<typeof mountParams>, value: unknown) {
  return w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === value)
}

describe('AudioTranscodeParams — 顯示', () => {
  it('output_format select 顯示目前值', () => {
    const w = mountParams({ output_format: 'aac' })
    const select = findSelectByModelValue(w, 'aac')
    expect(select).toBeTruthy()
  })

  it('wma 不入 UI 選單（schema 有、UI 過濾——沿舊 panel formats 常量）', () => {
    const w = mountParams({ output_format: 'mp3' })
    const select = w.findComponent(AppSelect)
    const values = (select.props('options') as Array<{ options: Array<{ value: string }> }>).flatMap(
      (g) => g.options.map((o) => o.value),
    )
    expect(values).not.toContain('wma')
    // 但涵蓋 schema 其餘全部 lossy/lossless 選項
    expect(values.sort()).toEqual(['aac', 'aiff', 'alac', 'flac', 'm4a', 'mp3', 'ogg', 'opus', 'wav'].sort())
  })
})

describe('AudioTranscodeParams — 無損隱藏 bitrate', () => {
  it('mp3（有損）→ bitrate 欄位顯示', () => {
    const w = mountParams({ output_format: 'mp3' })
    expect(w.text()).toContain('audio.transcode.bitrate')
  })

  it('wav（無損）→ bitrate 欄位隱藏', () => {
    const w = mountParams({ output_format: 'wav' })
    expect(w.text()).not.toContain('audio.transcode.bitrate')
  })

  it('flac/alac/aiff（無損）→ bitrate 欄位隱藏', () => {
    for (const fmt of ['flac', 'alac', 'aiff']) {
      const w = mountParams({ output_format: fmt })
      expect(w.text()).not.toContain('audio.transcode.bitrate')
    }
  })
})

describe('AudioTranscodeParams — bitrate 動態上限', () => {
  it('mp3 → 上限 320k（無額外選項）', () => {
    const w = mountParams({ output_format: 'mp3', audio_bitrate: '192k' })
    const bitrateSelect = w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === '192k')
    const values = (bitrateSelect!.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(values).toEqual(['', '128k', '192k', '256k', '320k'])
  })

  it('aac → 上限 512k，額外附加 512k 選項', () => {
    const w = mountParams({ output_format: 'aac', audio_bitrate: '192k' })
    const bitrateSelect = w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === '192k')
    const values = (bitrateSelect!.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(values).toEqual(['', '128k', '192k', '256k', '320k', '512k'])
  })
})

describe('AudioTranscodeParams — commit（欄位編輯 → emit）', () => {
  it('切格式 → emit update:params 含新 output_format', async () => {
    const w = mountParams({ output_format: 'mp3' })
    const select = w.findComponent(AppSelect)
    select.vm.$emit('update:modelValue', 'aac')
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ output_format: 'aac' })
  })

  it('sample_rate 選 44100 → emit sample_rate:44100（number）', async () => {
    const w = mountParams({ output_format: 'mp3' })
    const selects = w.findAllComponents(AppSelect)
    const sampleRate = selects.find((s) =>
      (s.props('options') as Array<{ value: string }>).some((o) => o.value === '44100'),
    )!
    sampleRate.vm.$emit('update:modelValue', '44100')
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ sample_rate: 44100 })
  })

  it('channels 選 2（新 UI）→ emit channels:2（number）', async () => {
    const w = mountParams({ output_format: 'mp3' })
    const selects = w.findAllComponents(AppSelect)
    const channelsSelect = selects.find((s) =>
      (s.props('options') as Array<{ value: string; label: string }>).some((o) => o.value === '2'),
    )!
    channelsSelect.vm.$emit('update:modelValue', '2')
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ channels: 2 })
  })

  it('channels 選回空字串（保持原始）→ emit channels:undefined', async () => {
    const w = mountParams({ output_format: 'mp3', channels: 2 })
    const selects = w.findAllComponents(AppSelect)
    const channelsSelect = selects.find((s) => s.props('modelValue') === '2')!
    channelsSelect.vm.$emit('update:modelValue', '')
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    expect(emitted[emitted.length - 1][0]).toMatchObject({ channels: undefined })
  })
})

describe('AudioTranscodeParams — 響應式衍生（外部寫入重推顯示）', () => {
  it('外部 setProps 改 output_format → select 顯示值同步更新', async () => {
    const w = mountParams({ output_format: 'mp3' })
    await w.setProps({ params: { output_format: 'flac' } })
    const select = findSelectByModelValue(w, 'flac')
    expect(select).toBeTruthy()
    // flac 為無損 → bitrate 欄位應隱藏
    expect(w.text()).not.toContain('audio.transcode.bitrate')
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("audio.transcode") === true', () => {
    expect(hasParamComponent('audio.transcode')).toBe(true)
  })

  it('METAS["audio.transcode"].toolKey === "audio.transcode"', () => {
    expect(METAS['audio.transcode'].toolKey).toBe('audio.transcode')
  })
})

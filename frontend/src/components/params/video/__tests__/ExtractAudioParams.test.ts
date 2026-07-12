/**
 * ExtractAudioParams.vue 單測（統一參數元件案批 1 Task 1.2）。
 * 小元件：audio_format select＋audio_bitrate select（wav/flac 隱藏）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import ExtractAudioParams from '../ExtractAudioParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'pipeline') {
  return mount(ExtractAudioParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

describe('ExtractAudioParams 渲染＋commit', () => {
  it('mount → audio_format select 顯示 params.audio_format', () => {
    const w = mountParams({ audio_format: 'mp3', audio_bitrate: '192k' })
    const selects = w.findAllComponents(AppSelect)
    expect(selects[0].props('modelValue')).toBe('mp3')
  })

  it('audio_format select 改值 → emit update:params 含新值＋保留其餘欄位', async () => {
    const w = mountParams({ audio_format: 'mp3', audio_bitrate: '192k' })
    const formatSelect = w.findAllComponents(AppSelect)[0]
    formatSelect.vm.$emit('update:modelValue', 'flac')
    await w.vm.$nextTick()

    expect(w.emitted('update:params')).toHaveLength(1)
    expect(w.emitted('update:params')![0][0]).toEqual({ audio_format: 'flac', audio_bitrate: '192k' })
  })

  it('audio_bitrate select 改值 → emit 新物件', async () => {
    const w = mountParams({ audio_format: 'mp3', audio_bitrate: '192k' })
    const bitrateSelect = w.findAllComponents(AppSelect)[1]
    bitrateSelect.vm.$emit('update:modelValue', '320k')
    await w.vm.$nextTick()

    expect(w.emitted('update:params')![0][0]).toEqual({ audio_format: 'mp3', audio_bitrate: '320k' })
  })
})

describe('ExtractAudioParams — wav/flac 隱藏位元率', () => {
  it('audio_format=mp3 → 位元率 select 顯示', () => {
    const w = mountParams({ audio_format: 'mp3' })
    expect(w.findAllComponents(AppSelect)).toHaveLength(2)
  })

  it('audio_format=wav → 位元率 select 隱藏', () => {
    const w = mountParams({ audio_format: 'wav' })
    expect(w.findAllComponents(AppSelect)).toHaveLength(1)
  })

  it('audio_format=flac → 位元率 select 隱藏', () => {
    const w = mountParams({ audio_format: 'flac' })
    expect(w.findAllComponents(AppSelect)).toHaveLength(1)
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("video.extract_audio") === true', async () => {
    const { hasParamComponent } = await import('../../index')
    expect(hasParamComponent('video.extract_audio')).toBe(true)
  })
})

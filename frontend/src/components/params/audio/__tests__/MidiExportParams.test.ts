/**
 * MidiExportParams.vue 單測（統一參數元件 spec §5；批 3 Task 3.5 Part B——最小侵入拆分）。
 * 覆蓋：渲染五格式選項（wav/mp3/flac/ogg/aac）、v-model 雙向（modelValue 讀 params.output_format
 * / 選擇後 emit update:params 含新 output_format，保留其餘既有欄位）。不掛 ToolParamHost（本檔
 * 不進 PARAM_COMPONENTS/METAS）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import MidiExportParams from '../MidiExportParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'

function mountParams(params: Record<string, unknown>) {
  return mount(MidiExportParams, {
    props: { params, context: 'tool', fileInfo: null },
    global: { mocks: { $t: (k: string) => k } },
  })
}

describe('MidiExportParams — 渲染五格式選項', () => {
  it('AppSelect options 恰為 wav/mp3/flac/ogg/aac 五格式', () => {
    const w = mountParams({ output_format: 'wav' })
    const select = w.findComponent(AppSelect)
    expect(select.exists()).toBe(true)
    const values = (select.props('options') as Array<{ value: string }>).map((o) => o.value)
    expect(values).toEqual(['wav', 'mp3', 'flac', 'ogg', 'aac'])
  })
})

describe('MidiExportParams — v-model 雙向', () => {
  it('modelValue = params.output_format', () => {
    const w = mountParams({ output_format: 'flac' })
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('flac')
  })

  it('未設 output_format → modelValue 預設 "wav"', () => {
    const w = mountParams({})
    const select = w.findComponent(AppSelect)
    expect(select.props('modelValue')).toBe('wav')
  })

  it('選擇 → emit update:params 含新 output_format，保留其餘既有欄位', async () => {
    const w = mountParams({ output_format: 'wav', other_field: 'keep-me' })
    const select = w.findComponent(AppSelect)
    await select.vm.$emit('update:modelValue', 'mp3')
    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.output_format).toBe('mp3')
    expect(last.other_field).toBe('keep-me')
  })
})

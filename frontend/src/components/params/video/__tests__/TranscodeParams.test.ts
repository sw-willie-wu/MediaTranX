/**
 * TranscodeParams.vue 單測（統一參數元件案批 1 Task 1.2）。
 * 覆蓋：context 過濾音訊格式、resolution custom 響應式衍生（one-shot）、依格式條件顯示、
 * CRF commit。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import TranscodeParams from '../TranscodeParams.vue'
import AppSelect from '@/components/common/AppSelect.vue'
import AppRange from '@/components/common/AppRange.vue'

function mockT(k: string): string {
  return k
}

function mountParams(params: Record<string, unknown>, context: 'tool' | 'pipeline' = 'tool') {
  return mount(TranscodeParams, {
    props: { params, context, fileInfo: null },
    global: {
      mocks: { $t: mockT },
    },
  })
}

/** AppSelect stub 用 modelValue 反查對應的實例（元件內同時掛多個 AppSelect） */
function findSelectByValue(w: ReturnType<typeof mountParams>, value: unknown) {
  return w.findAllComponents(AppSelect).find((s) => s.props('modelValue') === value)
}

describe('TranscodeParams — context 過濾（關閉 pipeline 音訊外洩 finding）', () => {
  it('tool context：output_format 選單含 mp3', () => {
    const w = mountParams({ output_format: 'mp4' }, 'tool')
    const formatSelect = w.findAllComponents(AppSelect)[0]
    const values = formatSelect.props('options').map((o: { value: string }) => o.value)
    expect(values).toContain('mp3')
  })

  it('pipeline context：output_format 選單不含 mp3/aac/wav/flac', () => {
    const w = mountParams({ output_format: 'mp4' }, 'pipeline')
    const formatSelect = w.findAllComponents(AppSelect)[0]
    const values = formatSelect.props('options').map((o: { value: string }) => o.value)
    expect(values).not.toContain('mp3')
    expect(values).not.toContain('aac')
    expect(values).not.toContain('wav')
    expect(values).not.toContain('flac')
  })
})

describe('TranscodeParams — resolution custom 響應式衍生（one-shot pattern）', () => {
  it('params={resolution:"1234x777"} → custom 模式，寬高欄顯示 1234/777', () => {
    const w = mountParams({ output_format: 'mp4', resolution: '1234x777' })
    const widthInput = w.find('.size-input-group input')
    expect(widthInput.exists()).toBe(true)
    const inputs = w.findAll('.size-inputs input[type="number"]')
    expect(inputs[0].element.value).toBe('1234')
    expect(inputs[1].element.value).toBe('777')
  })

  it('custom 模式下改寬 1280＋commit(change) → emit resolution "1280x777"', async () => {
    const w = mountParams({ output_format: 'mp4', resolution: '1234x777' })
    const inputs = w.findAll('.size-inputs input[type="number"]')
    await inputs[0].setValue(1280)

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last.resolution).toBe('1280x777')
  })

  it('外部 setProps params={resolution:"1920x1080"}（預設清單值）→ custom 模式退出、AppSelect 顯示 1080p', async () => {
    const w = mountParams({ output_format: 'mp4', resolution: '1234x777' })
    expect(w.find('.size-inputs').exists()).toBe(true)

    await w.setProps({ params: { output_format: 'mp4', resolution: '1920x1080' } })

    expect(w.find('.size-inputs').exists()).toBe(false)
    const resolutionSelect = findSelectByValue(w, '1920x1080')
    expect(resolutionSelect).toBeTruthy()
  })
})

describe('TranscodeParams — 依格式條件顯示', () => {
  it('mp4：視訊編碼/CRF 顯示於進階區（SettingsCollapsible）、fps/位元率不顯示', () => {
    const w = mountParams({ output_format: 'mp4' })
    const advanced = w.find('.settings-collapsible-body')
    expect(advanced.exists()).toBe(true)
    expect(advanced.findComponent(AppRange).exists()).toBe(true)
    const videoCodecSelect = findSelectByValue(w, 'h264')
    expect(videoCodecSelect).toBeTruthy()
    expect(videoCodecSelect!.element.closest('.settings-collapsible-body')).toBeTruthy()
  })

  it('mp4：頂層預設視圖僅輸出格式＋解析度，video_codec/crf 不在頂層（在 SettingsCollapsible 內）', () => {
    const w = mountParams({ output_format: 'mp4' })
    const topLevelGroups = w
      .findAll('.form-group')
      .filter((g) => !g.element.closest('.settings-collapsible'))
    // 頂層只剩：輸出格式 + 解析度（純視訊格式無 custom 尺寸欄，resolution 為預設空值）
    expect(topLevelGroups).toHaveLength(2)
    const range = w.findComponent(AppRange)
    expect(range.element.closest('.settings-collapsible')).toBeTruthy()
  })

  it('格式切 gif → CRF/視訊編碼控件消失、fps 出現', async () => {
    const w = mountParams({ output_format: 'mp4' })
    await w.setProps({ params: { output_format: 'gif' } })

    expect(w.findComponent(AppRange).exists()).toBe(false)
    expect(findSelectByValue(w, 'h264')).toBeFalsy()
    expect(findSelectByValue(w, '12')).toBeTruthy() // fps default
  })

  it('格式切 mp3（tool）→ 位元率出現；wav → 位元率消失', async () => {
    const w = mountParams({ output_format: 'mp4' }, 'tool')
    await w.setProps({ params: { output_format: 'mp3' } })
    expect(findSelectByValue(w, '192k')).toBeTruthy()

    await w.setProps({ params: { output_format: 'wav' } })
    expect(findSelectByValue(w, '192k')).toBeFalsy()
  })

  it('音訊格式：視訊控制列（video_codec/preset/audio_codec/scale_algorithm）全不顯示、僅位元率', () => {
    const w = mountParams({ output_format: 'mp3' }, 'tool')
    expect(w.findComponent(AppRange).exists()).toBe(false)
    expect(findSelectByValue(w, 'h264')).toBeFalsy()
    expect(findSelectByValue(w, 'medium')).toBeFalsy()
    expect(findSelectByValue(w, 'aac')).toBeFalsy()
  })
})

describe('TranscodeParams — CRF commit', () => {
  it('crf AppRange 改值 → emit {crf: N} 新物件（含其餘既有欄位）', async () => {
    const w = mountParams({ output_format: 'mp4', video_codec: 'h264' })
    const range = w.findComponent(AppRange)
    range.vm.$emit('update:modelValue', 30)
    await w.vm.$nextTick()

    const emitted = w.emitted('update:params')!
    const last = emitted[emitted.length - 1][0] as Record<string, unknown>
    expect(last).toEqual({ output_format: 'mp4', video_codec: 'h264', crf: 30 })
  })
})

describe('params/index.ts 載入表', () => {
  it('hasParamComponent("video.transcode") === true', async () => {
    const { hasParamComponent } = await import('../../index')
    expect(hasParamComponent('video.transcode')).toBe(true)
  })

  it('hasParamComponent("video.extract_audio") === true', async () => {
    const { hasParamComponent } = await import('../../index')
    expect(hasParamComponent('video.extract_audio')).toBe(true)
  })
})

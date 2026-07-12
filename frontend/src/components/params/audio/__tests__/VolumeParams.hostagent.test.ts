/**
 * ToolParamHost + VolumeParams 合掛整合測（統一參數元件 spec §6；批 3 Task 3.1）。
 * 取代舊 AudioVolumePanel.agent.test.ts——host 接手 agent 掛載後，唯一權威測試點；
 * 本檔專注 host×元件整合，特別驗證 agentRequiresConfirm:false（批 3 第一個不同者，
 * 沿舊 AudioVolumePanel.agentSchema.execute.requiresConfirm）與 gainPreview 經 host
 * 單根元件 attrs fallthrough 穿透（沿 CropParams.hostagent.test.ts 先例）。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

const submitTaskMock = vi.hoisted(() => vi.fn())
const isProcessingState = vi.hoisted(() => ({ value: false }))
vi.mock('@/composables/useSubmitTask', () => ({
  useSubmitTask: () => ({ submitTask: submitTaskMock, isProcessing: isProcessingState }),
}))

const capturedHandle = vi.hoisted(() => ({ current: null as any }))
vi.mock('@/composables/useAgentPanelHost', () => ({
  useAgentPanelHost: (_panelId: string, handle: any) => {
    capturedHandle.current = handle
  },
}))

vi.mock('@/composables/useModelGuard', () => ({
  useModelGuard: () => ({ guardModelReady: vi.fn(async () => true) }),
}))
vi.mock('@/stores/models', () => ({
  useModelStore: () => ({ models: [] }),
}))

import ToolParamHost from '@/components/params/ToolParamHost.vue'
// 預先靜態 import 讓 VolumeParams.vue 先進 vitest 模組快取（見 CutParams.hostagent.test.ts 同段註記）。
import '@/components/params/audio/VolumeParams.vue'

function mountHost(props: Record<string, unknown> = {}) {
  return mount(ToolParamHost, {
    props: {
      toolKey: 'audio.volume',
      panelId: 'audio.volume',
      fileId: 'f1',
      currentFileName: 'clip.mp3',
      fileInfo: null,
      ...props,
    },
    global: {
      mocks: { $t: (k: string) => k },
    },
  })
}

beforeEach(() => {
  submitTaskMock.mockReset()
  isProcessingState.value = false
  capturedHandle.current = null
})

describe('VolumeParams × ToolParamHost — agentSchema（批 3 第一個不同者：requiresConfirm=false）', () => {
  it('1. fields=[volume_db,normalize]；agentSchema.execute.requiresConfirm=false（沿舊 AudioVolumePanel）', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current
    expect(handle).toBeTruthy()

    const fields = handle.agentSchema.fields
    expect(fields.map((f: any) => f.name)).toEqual(['volume_db', 'normalize'])
    expect(fields.find((f: any) => f.name === 'volume_db').min).toBe(-30)
    expect(fields.find((f: any) => f.name === 'volume_db').max).toBe(30)

    expect(handle.agentSchema.execute.requiresConfirm).toBe(false)
    expect(handle.agentSchema.execute.label).toBe('panel.volume.execute')

    w.unmount()
  })
})

describe('VolumeParams × ToolParamHost — setField + getSubmitSpec（agent 寫入路徑）', () => {
  it('2. setField(volume_db, "-12") → coerce number；getSubmitSpec 分流 labelKey=adjust_label', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    expect(handle.setField('volume_db', '-12')).toBe(-12)

    const spec = w.vm.getSubmitSpec()
    expect(spec).toEqual({
      apiPath: '/audio/volume',
      payload: { volume_db: -12, normalize: false },
      taskType: 'audio.volume',
      labelKey: 'audio.volume.adjust_label',
    })
    expect(spec.payload).not.toHaveProperty('file_id')

    w.unmount()
  })

  it('3. setField(normalize, true) → getSubmitSpec 歸零 volume_db、labelKey=normalize_label', async () => {
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('volume_db', 18)
    handle.setField('normalize', true)

    const spec = w.vm.getSubmitSpec()
    expect(spec.payload).toEqual({ volume_db: 0, normalize: true })
    expect(spec.labelKey).toBe('audio.volume.normalize_label')

    w.unmount()
  })
})

describe('VolumeParams × ToolParamHost — execute 分流', () => {
  it('4a. adjust 模式 → submitTask 收到 file_id + volume_db + normalize:false，label=adjust_label', async () => {
    submitTaskMock.mockResolvedValue('tid-adjust')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('volume_db', 6)
    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/volume',
      { file_id: 'f1', volume_db: 6, normalize: false },
      'audio.volume.adjust_label',
      'audio.volume',
      'clip.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-adjust' })
    expect(w.emitted('submit')).toEqual([['tid-adjust']])

    w.unmount()
  })

  it('4b. normalize 模式 → submitTask 收到 volume_db:0，label=normalize_label', async () => {
    submitTaskMock.mockResolvedValue('tid-normalize')
    const w = mountHost()
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('volume_db', 6)
    handle.setField('normalize', true)
    const result = await handle.execute()

    expect(submitTaskMock).toHaveBeenCalledWith(
      '/audio/volume',
      { file_id: 'f1', volume_db: 0, normalize: true },
      'audio.volume.normalize_label',
      'audio.volume',
      'clip.mp3',
    )
    expect(result).toEqual({ task_id: 'tid-normalize' })
    expect(w.emitted('submit')).toEqual([['tid-normalize']])

    w.unmount()
  })
})

describe('VolumeParams × ToolParamHost — gainPreview 單根元件 attrs fallthrough（沿 CropParams 先例）', () => {
  it('5. @update:gain-preview 掛在 <ToolParamHost> → VolumeParams 掛載 immediate emit 穿透到父層', async () => {
    const onGainPreview = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'audio.volume',
        panelId: 'audio.volume',
        fileId: 'f1',
        currentFileName: 'clip.mp3',
        fileInfo: null,
        'onUpdate:gainPreview': onGainPreview,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()

    expect(onGainPreview).toHaveBeenCalledWith(1) // 預設 volume_db=0 → gain=1

    w.unmount()
  })

  it('6. agent setField(volume_db, 20) → gainPreview 穿透更新為 10', async () => {
    const onGainPreview = vi.fn()
    const w = mount(ToolParamHost, {
      props: {
        toolKey: 'audio.volume',
        panelId: 'audio.volume',
        fileId: 'f1',
        currentFileName: 'clip.mp3',
        fileInfo: null,
        'onUpdate:gainPreview': onGainPreview,
      },
      global: {
        mocks: { $t: (k: string) => k },
      },
    })
    await flushPromises()
    const handle = capturedHandle.current

    handle.setField('volume_db', 20)
    await flushPromises()

    expect(onGainPreview).toHaveBeenLastCalledWith(10)

    w.unmount()
  })
})

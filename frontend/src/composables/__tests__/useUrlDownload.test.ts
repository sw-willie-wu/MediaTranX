import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const apiFetch = vi.fn()
vi.mock('@/composables/useApi', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))
const toastShow = vi.fn()
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: toastShow }) }))
const refreshTasks = vi.fn()
const startPolling = vi.fn()
vi.mock('@/stores/tasks', () => ({
  useTaskStore: () => ({ refreshTasks, startPolling }),
}))

import { useUrlDownload, buildFormatIntent } from '@/composables/useUrlDownload'
import { useVideoDownloadStore } from '@/stores/videoDownload'

function jsonRes(body: unknown, ok = true) {
  return { ok, json: async () => body } as Response
}

describe('buildFormatIntent', () => {
  it('auto → mode only', () => {
    expect(buildFormatIntent({ quality_mode: 'auto', max_height: 1080 }, '')).toEqual({ mode: 'auto' })
  })
  it('cap → carries max_height', () => {
    expect(buildFormatIntent({ quality_mode: 'cap', max_height: 720 }, '')).toEqual({ mode: 'cap', max_height: 720 })
  })
  it('ask → carries selected format_id', () => {
    expect(buildFormatIntent({ quality_mode: 'ask', max_height: 1080 }, '137')).toEqual({ mode: 'ask', format_id: '137' })
  })
})

describe('useUrlDownload', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiFetch.mockReset(); toastShow.mockReset(); refreshTasks.mockReset(); startPolling.mockReset()
    useUrlDownload().cancel() // reset singleton state
  })

  it('no-ops when feature disabled (fail-closed)', async () => {
    const u = useUrlDownload()
    await u.handlePastedUrl('https://x.com/v')
    expect(u.visible.value).toBe(false)
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it('probes and shows card when downloadable', async () => {
    useVideoDownloadStore().settings.enabled = true
    apiFetch.mockResolvedValueOnce(jsonRes({
      downloadable: true, title: 'Clip', duration: 12,
      formats: [{ format_id: '137', height: 1080, ext: 'mp4', note: '1080p' }],
    }))
    const u = useUrlDownload()
    await u.handlePastedUrl('https://x.com/v')
    expect(u.visible.value).toBe(true)
    expect(u.probe.value?.title).toBe('Clip')
    expect(u.selectedFormatId.value).toBe('137')
    expect(u.error.value).toBe('')
  })

  it('surfaces reason when not downloadable', async () => {
    useVideoDownloadStore().settings.enabled = true
    apiFetch.mockResolvedValueOnce(jsonRes({ downloadable: false, reason: 'private' }))
    const u = useUrlDownload()
    await u.handlePastedUrl('https://x.com/v')
    expect(u.visible.value).toBe(true)
    expect(u.error.value).toBe('private')
    expect(u.probe.value).toBeNull()
  })

  it('confirm() submits download with the built format_intent and starts polling', async () => {
    const store = useVideoDownloadStore()
    store.settings.enabled = true
    store.settings.quality_mode = 'cap'
    store.settings.max_height = 720
    apiFetch.mockResolvedValueOnce(jsonRes({ downloadable: true, title: 'Clip', formats: [] }))
    const u = useUrlDownload()
    await u.handlePastedUrl('https://x.com/v')
    apiFetch.mockResolvedValueOnce(jsonRes({ task_id: 'tid' }))
    await u.confirm()
    const [path, init] = apiFetch.mock.calls[1]
    expect(path).toBe('/video/download')
    const body = JSON.parse(init.body)
    expect(body.url).toBe('https://x.com/v')
    expect(body.title).toBe('Clip')
    expect(body.format_intent).toEqual({ mode: 'cap', max_height: 720 })
    expect(startPolling).toHaveBeenCalled()
    expect(u.visible.value).toBe(false) // card hides after submit
  })
})

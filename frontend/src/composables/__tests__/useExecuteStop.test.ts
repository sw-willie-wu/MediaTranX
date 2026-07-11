import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref, computed, watch, nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import type { MediaEntry } from '@/composables/useMediaCollection'

const confirmMock = vi.fn<(opts: unknown) => Promise<boolean>>()
const toastShow = vi.fn()
vi.mock('@/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: confirmMock }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: toastShow }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string, p?: Record<string, unknown>) => (p ? `${k}:${JSON.stringify(p)}` : k) } } }))

import { useExecuteStop } from '@/composables/useExecuteStop'

function makeEntry(patch: Partial<MediaEntry>): MediaEntry {
  return {
    id: crypto.randomUUID(), file: null, fileName: 'f', fileSize: 1, fileId: 'fid',
    previewUrl: 'u', thumbnailUrl: 'u', status: 'idle', progress: 0,
    historyStack: [], redoStack: [], currentTaskId: null, ...patch,
  }
}

function setup(entries: MediaEntry[]) {
  const list = ref<MediaEntry[]>(entries)
  const collection = { entriesList: computed(() => list.value) }
  const stop = useExecuteStop(collection)
  return { list, ...stop }
}

const fetchMock = vi.fn()

beforeEach(() => {
  setActivePinia(createPinia())
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset().mockResolvedValue({ ok: true })
  confirmMock.mockReset()
  toastShow.mockReset()
})

describe('useExecuteStop', () => {
  it('confirm 取消 → 零副作用（不打 API、isCanceling false）', async () => {
    confirmMock.mockResolvedValue(false)
    const s = setup([makeEntry({ status: 'processing', currentTaskId: 't1' })])
    await s.requestStop()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(s.isCanceling.value).toBe(false)
  })

  it('confirm 後枚舉全部 processing entries → 逐一 cancel、isCanceling true', async () => {
    confirmMock.mockResolvedValue(true)
    const s = setup([
      makeEntry({ status: 'processing', currentTaskId: 't1' }),
      makeEntry({ status: 'processing', currentTaskId: 't2' }),
      makeEntry({ status: 'idle', currentTaskId: null }),
    ])
    await s.requestStop()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/tasks/t1/cancel')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/tasks/t2/cancel')
    expect(s.isCanceling.value).toBe(true)
  })

  it('entries 收斂（idle + currentTaskId null）→ isCanceling 自動歸 false', async () => {
    confirmMock.mockResolvedValue(true)
    const e = makeEntry({ status: 'processing', currentTaskId: 't1' })
    const s = setup([e])
    await s.requestStop()
    expect(s.isCanceling.value).toBe(true)
    s.list.value = [{ ...e, status: 'idle', currentTaskId: null }]
    await nextTick()
    expect(s.isCanceling.value).toBe(false)
  })

  it('confirm 停留期間任務全結束 → 空枚舉 no-op', async () => {
    const e = makeEntry({ status: 'processing', currentTaskId: 't1' })
    const s = setup([e])
    confirmMock.mockImplementation(async () => {
      // 對話框開著時任務收斂
      s.list.value = [{ ...e, status: 'idle', currentTaskId: null }]
      return true
    })
    await s.requestStop()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(s.isCanceling.value).toBe(false)
  })

  it('cancel HTTP 失敗 → toast、該 id 移出追蹤；成功者仍追蹤', async () => {
    confirmMock.mockResolvedValue(true)
    fetchMock
      .mockResolvedValueOnce({ ok: true })    // t1 成功
      .mockResolvedValueOnce({ ok: false })   // t2 失敗
    const e1 = makeEntry({ status: 'processing', currentTaskId: 't1' })
    const e2 = makeEntry({ status: 'processing', currentTaskId: 't2' })
    const s = setup([e1, e2])
    await s.requestStop()
    expect(toastShow).toHaveBeenCalledTimes(1)
    expect(s.isCanceling.value).toBe(true)          // t1 仍 processing → true
    s.list.value = [{ ...e1, status: 'idle', currentTaskId: null }, e2]
    await nextTick()
    expect(s.isCanceling.value).toBe(false)         // t2 不在追蹤中 → false
  })

  it('isCanceling 對已訂閱者即時翻 true（cancelingIds 必須 reactive，spec §4.2）', async () => {
    confirmMock.mockResolvedValue(true)
    const s = setup([makeEntry({ status: 'processing', currentTaskId: 't1' })])
    // 模擬 template 綁定：先訂閱＋先讀一次讓 computed 進入 cached 狀態
    const seen: boolean[] = []
    watch(s.isCanceling, v => seen.push(v))
    expect(s.isCanceling.value).toBe(false)
    await s.requestStop()
    await nextTick()
    // 裸 Set 版本：set 變動不是 computed 依賴 → 快取永遠 false、watcher 永不觸發
    expect(s.isCanceling.value).toBe(true)
    expect(seen).toContain(true)
  })

  it('每輪覆蓋：上一輪殘留 id 不影響新一輪', async () => {
    confirmMock.mockResolvedValue(true)
    const e1 = makeEntry({ status: 'processing', currentTaskId: 't1' })
    const s = setup([e1])
    await s.requestStop()
    s.list.value = [{ ...e1, status: 'idle', currentTaskId: null }]
    await nextTick()
    // 第二輪：新任務 t9
    const e9 = makeEntry({ status: 'processing', currentTaskId: 't9' })
    s.list.value = [e9]
    await s.requestStop()
    expect(s.isCanceling.value).toBe(true)
    expect(String(fetchMock.mock.calls.at(-1)![0])).toContain('/tasks/t9/cancel')
  })
})

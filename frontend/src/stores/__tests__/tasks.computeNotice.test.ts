import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

const showMock = vi.fn()
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: showMock }) }))

// Mock @/i18n: the default export needs .global.t for the lazy import in tasks.ts
vi.mock('@/i18n', () => ({
  default: { global: { t: (key: string) => key } },
}))

import { useTaskStore } from '@/stores/tasks'

describe('tasks store compute notices', () => {
  beforeEach(() => { setActivePinia(createPinia()); showMock.mockClear() })

  it('shows a warning toast once per unique notice', async () => {
    const store = useTaskStore()
    const taskData = {
      task_id: 't1', task_type: 'video.subtitle', status: 'processing',
      progress: 0.3, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      notices: [{ code: 'vram_insufficient', params: { model: 'whisper-medium' } }],
    }
    store.applyTaskUpdates([taskData] as never)
    store.applyTaskUpdates([{ ...taskData, progress: 0.5 }] as never)
    await flushPromises()
    expect(showMock).toHaveBeenCalledTimes(1)
    expect(showMock).toHaveBeenCalledWith(expect.any(String), { type: 'warning' })
  })
})

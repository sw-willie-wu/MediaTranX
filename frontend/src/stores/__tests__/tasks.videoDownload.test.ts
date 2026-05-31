import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'

const { adopt } = vi.hoisted(() => ({ adopt: vi.fn() }))
vi.mock('@/composables/videoDownloadComplete', () => ({ adoptCompletedDownload: adopt }))

import { useTaskStore } from '@/stores/tasks'

function fetchReturning(tasks: unknown[]) {
  return vi.fn().mockResolvedValue({ ok: true, json: async () => tasks } as Response)
}

const base = {
  task_id: 't1', task_type: 'video.download', progress: 1, message: null,
  error: null, created_at: '2026-05-30T00:00:00Z', updated_at: '2026-05-30T00:00:01Z',
}

describe('tasks store — video.download completion handoff', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    adopt.mockReset()
  })

  it('calls adoptCompletedDownload on transition to completed', async () => {
    const store = useTaskStore()
    const result = { output_file_id: 'fid', output_filename: 'c.mp4', output_size: 5, title: 'C' }

    // 1st poll: processing (no adopt)
    vi.stubGlobal('fetch', fetchReturning([{ ...base, status: 'processing', result: null }]))
    await store.refreshTasks()
    expect(adopt).not.toHaveBeenCalled()

    // 2nd poll: completed (adopt once)
    vi.stubGlobal('fetch', fetchReturning([{ ...base, status: 'completed', result }]))
    await store.refreshTasks()
    await flushPromises()
    expect(adopt).toHaveBeenCalledTimes(1)
    expect(adopt).toHaveBeenCalledWith(result)
  })

  it('ignores completion for other task types', async () => {
    const store = useTaskStore()
    vi.stubGlobal('fetch', fetchReturning([
      { ...base, task_id: 't2', task_type: 'video.cut', status: 'processing', result: null },
    ]))
    await store.refreshTasks()
    vi.stubGlobal('fetch', fetchReturning([
      { ...base, task_id: 't2', task_type: 'video.cut', status: 'completed',
        result: { output_file_id: 'x', output_filename: 'x.mp4', output_size: 1 } },
    ]))
    await store.refreshTasks()
    await flushPromises()
    expect(adopt).not.toHaveBeenCalled()
  })
})

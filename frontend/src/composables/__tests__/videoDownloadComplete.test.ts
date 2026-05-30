import { describe, it, expect, vi, beforeEach } from 'vitest'

const { setPendingResults, toastShow, push } = vi.hoisted(() => ({
  setPendingResults: vi.fn(),
  toastShow: vi.fn(),
  push: vi.fn(),
}))

vi.mock('@/stores/files', () => ({ useFilesStore: () => ({ setPendingResults }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: toastShow }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string) => k } } }))
vi.mock('@/router', () => ({ default: { push } }))

import { adoptCompletedDownload } from '@/composables/videoDownloadComplete'

describe('adoptCompletedDownload', () => {
  beforeEach(() => {
    setPendingResults.mockReset(); toastShow.mockReset(); push.mockReset()
  })

  it('sets pending results + dispatches the ready event + toast', () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    adoptCompletedDownload({
      output_file_id: 'fid', output_filename: 'clip.mp4', output_size: 99, title: 'Clip',
    })
    expect(setPendingResults).toHaveBeenCalledWith([
      { fileId: 'fid', filename: 'clip.mp4', fileSize: 99, mimeType: 'video/mp4' },
    ])
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'pending-results-ready' }))
    expect(toastShow).toHaveBeenCalled()
    // toast action navigates to the video tool
    const opts = toastShow.mock.calls[0][1]
    opts.action.callback()
    expect(push).toHaveBeenCalledWith('/video')
  })
})

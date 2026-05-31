import { describe, it, expect, vi, beforeEach } from 'vitest'

const { queueVideoDownload, toastShow, push, currentRoute } = vi.hoisted(() => ({
  queueVideoDownload: vi.fn(),
  toastShow: vi.fn(),
  push: vi.fn().mockResolvedValue(undefined),
  currentRoute: { value: { path: '/' } },
}))

vi.mock('@/stores/files', () => ({ useFilesStore: () => ({ queueVideoDownload }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: toastShow }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string) => k } } }))
vi.mock('@/router', () => ({ default: { push, currentRoute } }))

import { adoptCompletedDownload } from '@/composables/videoDownloadComplete'

const RESULT = {
  output_file_id: 'fid',
  output_filename: 'clip.mp4',
  output_size: 99,
  title: 'Clip',
}

const EXPECTED_REF = { fileId: 'fid', filename: 'clip.mp4', fileSize: 99, mimeType: 'video/mp4' }

describe('adoptCompletedDownload', () => {
  beforeEach(() => {
    queueVideoDownload.mockReset()
    toastShow.mockReset()
    push.mockReset().mockResolvedValue(undefined)
    currentRoute.value.path = '/'  // default: not on the video tool
  })

  it('queues the download, dispatches video-download-ready, and shows the toast', () => {
    const captured: Event[] = []
    vi.spyOn(window, 'dispatchEvent').mockImplementation((e) => {
      captured.push(e)
      return true
    })

    adoptCompletedDownload(RESULT)

    // staged into the video-specific queue (NOT the generic pending-results)
    expect(queueVideoDownload).toHaveBeenCalledWith(EXPECTED_REF)

    // video-only CustomEvent dispatched
    expect(captured).toHaveLength(1)
    expect(captured[0]).toBeInstanceOf(CustomEvent)
    expect(captured[0].type).toBe('video-download-ready')

    // toast: success + "go to video tool" action
    expect(toastShow).toHaveBeenCalledOnce()
    const [msg, opts] = toastShow.mock.calls[0]
    expect(msg).toBe('video_download.toast.complete')
    expect(opts.type).toBe('success')
    expect(opts.action.label).toBe('video_download.toast.open')
  })

  it('the toast action navigates to the Video tool (no re-staging/dispatch)', () => {
    vi.spyOn(window, 'dispatchEvent').mockReturnValue(true)
    adoptCompletedDownload(RESULT)
    const callback = toastShow.mock.calls[0][1].action.callback

    queueVideoDownload.mockClear()
    callback()

    expect(push).toHaveBeenCalledWith('/video')
    // delivery already happened at completion; the action only navigates
    expect(queueVideoDownload).not.toHaveBeenCalled()
  })

  it('omits the go-to-video action when already on the Video tool (push would be a no-op)', () => {
    vi.spyOn(window, 'dispatchEvent').mockReturnValue(true)
    currentRoute.value.path = '/video'

    adoptCompletedDownload(RESULT)

    // still shows the success toast (download completed + auto-loaded)…
    expect(toastShow).toHaveBeenCalledOnce()
    const [msg, opts] = toastShow.mock.calls[0]
    expect(msg).toBe('video_download.toast.complete')
    expect(opts.type).toBe('success')
    // …but no redundant "go to video tool" button (you're already there)
    expect(opts.action).toBeUndefined()
  })
})

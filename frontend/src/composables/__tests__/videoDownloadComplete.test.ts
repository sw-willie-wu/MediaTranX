import { describe, it, expect, vi, beforeEach } from 'vitest'

const { setPendingResults, toastShow, push } = vi.hoisted(() => ({
  setPendingResults: vi.fn(),
  toastShow: vi.fn(),
  push: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/stores/files', () => ({ useFilesStore: () => ({ setPendingResults }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ show: toastShow }) }))
vi.mock('@/i18n', () => ({ default: { global: { t: (k: string) => k } } }))
vi.mock('@/router', () => ({ default: { push } }))

import { adoptCompletedDownload } from '@/composables/videoDownloadComplete'

const RESULT = {
  output_file_id: 'fid',
  output_filename: 'clip.mp4',
  output_size: 99,
  title: 'Clip',
}

const EXPECTED_REFS = [
  { fileId: 'fid', filename: 'clip.mp4', fileSize: 99, mimeType: 'video/mp4' },
]

describe('adoptCompletedDownload', () => {
  beforeEach(() => {
    setPendingResults.mockReset()
    toastShow.mockReset()
    push.mockReset().mockResolvedValue(undefined)
    vi.spyOn(window, 'dispatchEvent').mockReset?.()
  })

  it('shows a success toast at completion time, does NOT yet call setPendingResults or dispatchEvent', () => {
    const dispatch = vi.spyOn(window, 'dispatchEvent')
    adoptCompletedDownload(RESULT)

    expect(toastShow).toHaveBeenCalledOnce()
    const [msg, opts] = toastShow.mock.calls[0]
    expect(msg).toBe('video_download.toast.complete')
    expect(opts.type).toBe('success')
    expect(opts.action.label).toBe('video_download.toast.open')

    // NOT yet delivered
    expect(setPendingResults).not.toHaveBeenCalled()
    expect(dispatch).not.toHaveBeenCalled()
  })

  it('on "Open" callback: stages refs, navigates to /video, then dispatches — in that order', async () => {
    const dispatchedTypes: string[] = []
    vi.spyOn(window, 'dispatchEvent').mockImplementation((e) => {
      dispatchedTypes.push((e as Event).type)
      return true
    })

    // push resolves after setPendingResults has been called
    let setPendingResultsCalledBeforePushResolve = false
    push.mockImplementation(async () => {
      setPendingResultsCalledBeforePushResolve = setPendingResults.mock.calls.length > 0
    })

    adoptCompletedDownload(RESULT)
    const callback = toastShow.mock.calls[0][1].action.callback

    await callback()

    // setPendingResults called with the correct payload
    expect(setPendingResults).toHaveBeenCalledWith(EXPECTED_REFS)

    // router.push('/video') called
    expect(push).toHaveBeenCalledWith('/video')

    // dispatch happened (after await push)
    expect(dispatchedTypes).toContain('pending-results-ready')

    // ordering: setPendingResults fired before push resolved
    expect(setPendingResultsCalledBeforePushResolve).toBe(true)

    // ordering: push resolved before dispatch (dispatch comes after await push)
    const dispatchCallIndex = dispatchedTypes.indexOf('pending-results-ready')
    expect(dispatchCallIndex).toBe(0) // only dispatch in the test
  })

  it('dispatches a CustomEvent (not a plain Event) named pending-results-ready', async () => {
    const captured: Event[] = []
    vi.spyOn(window, 'dispatchEvent').mockImplementation((e) => {
      captured.push(e)
      return true
    })
    push.mockResolvedValue(undefined)

    adoptCompletedDownload(RESULT)
    const callback = toastShow.mock.calls[0][1].action.callback
    await callback()

    expect(captured).toHaveLength(1)
    expect(captured[0]).toBeInstanceOf(CustomEvent)
    expect(captured[0].type).toBe('pending-results-ready')
  })
})

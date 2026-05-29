import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useResultsStore, type ResultEntry } from '@/stores/results'
import { useFilesStore } from '@/stores/files'
import type { Router } from 'vue-router'

const ENTRY: ResultEntry = {
  fileId: 'vid1', filename: 'out.mp4', filePath: '/tmp/out.mp4',
  fileSize: 123, mimeType: 'video/mp4', createdAt: '', toolId: 'video.transcode',
}

describe('results openInTool — reference, no fetch', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('sets pendingResults + navigates, does NOT fetch the file', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)   // jsdom may not provide fetch; stub avoids spyOn-throws
    const rs = useResultsStore()
    rs.results.push({ ...ENTRY })
    const router = { push: vi.fn().mockResolvedValue(undefined) } as unknown as Router

    await rs.openInTool('vid1', router, '/image')   // current route != /video

    const fs = useFilesStore()
    const pending = fs.consumePendingResults()
    expect(pending).toEqual([{ fileId: 'vid1', filename: 'out.mp4', fileSize: 123, mimeType: 'video/mp4' }])
    expect(router.push).toHaveBeenCalledWith('/video')
    expect(fetchMock).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('same-route dispatches pending-results-ready instead of navigating', async () => {
    const rs = useResultsStore()
    rs.results.push({ ...ENTRY })
    const router = { push: vi.fn() } as unknown as Router
    const evSpy = vi.fn()
    window.addEventListener('pending-results-ready', evSpy)

    await rs.openInTool('vid1', router, '/video')   // already on target

    expect(router.push).not.toHaveBeenCalled()
    expect(evSpy).toHaveBeenCalledOnce()
    window.removeEventListener('pending-results-ready', evSpy)
  })
})

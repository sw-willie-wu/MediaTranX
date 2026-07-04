import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Fresh module each test so the module-level `subscribed` flag resets.
async function freshStore() {
  vi.resetModules()
  const mod = await import('@/stores/update')
  return mod.useUpdateStore()
}

function makeElectron(overrides: Record<string, unknown> = {}) {
  return {
    getUpdatePrefs: vi.fn(async () => ({ frequency: 'monthly', pendingInstaller: null })),
    checkForUpdates: vi.fn(async () => ({ status: 'up-to-date', current: '1.5.2', latest: '1.5.2' })),
    downloadUpdate: vi.fn(async () => ({ path: 'C:/updates/MediaTranX-Setup-1.6.0-full-win.exe' })),
    runInstaller: vi.fn(async () => ({ ok: true })),
    setUpdateFrequency: vi.fn(),
    onUpdateAvailable: vi.fn(),
    onUpdateDownloadProgress: vi.fn(),
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  delete (window as any).electron
})

describe('useUpdateStore', () => {
  it('init loads prefs and subscribes to main pushes', async () => {
    const e = makeElectron()
    ;(window as any).electron = e
    const store = await freshStore()
    await store.init()
    expect(store.frequency).toBe('monthly')
    expect(e.getUpdatePrefs).toHaveBeenCalledOnce()
    expect(e.onUpdateAvailable).toHaveBeenCalledOnce()
    expect(e.onUpdateDownloadProgress).toHaveBeenCalledOnce()
  })

  it('init called twice subscribes only once (idempotent)', async () => {
    const e = makeElectron()
    ;(window as any).electron = e
    const store = await freshStore()
    await store.init()
    await store.init()
    expect(e.onUpdateAvailable).toHaveBeenCalledOnce()
    expect(e.onUpdateDownloadProgress).toHaveBeenCalledOnce()
    // prefs may be re-read, but subscription must not stack
    expect(e.getUpdatePrefs).toHaveBeenCalledTimes(2)
  })

  it('onUpdateAvailable push opens the modal', async () => {
    const e = makeElectron()
    let pushCb: ((r: unknown) => void) | undefined
    e.onUpdateAvailable = vi.fn((cb: (r: unknown) => void) => { pushCb = cb })
    ;(window as any).electron = e
    const store = await freshStore()
    await store.init()
    pushCb!({ status: 'update-available', current: '1.5.2', latest: '1.6.0', asset: {} })
    expect(store.modalVisible).toBe(true)
    expect(store.latest).toBe('1.6.0')
  })

  it('checkManually: up-to-date sets status, no modal', async () => {
    ;(window as any).electron = makeElectron()
    const store = await freshStore()
    await store.checkManually()
    expect(store.status).toBe('up-to-date')
    expect(store.modalVisible).toBe(false)
  })

  it('checkManually: update-available opens the modal', async () => {
    ;(window as any).electron = makeElectron({
      checkForUpdates: vi.fn(async () => ({
        status: 'update-available', current: '1.5.2', latest: '1.6.0', asset: {},
      })),
    })
    const store = await freshStore()
    await store.checkManually()
    expect(store.status).toBe('update-available')
    expect(store.modalVisible).toBe(true)
  })

  it('checkManually: error sets lastError', async () => {
    ;(window as any).electron = makeElectron({
      checkForUpdates: vi.fn(async () => ({ status: 'error', current: '1.5.2', error: 'rate_limit' })),
    })
    const store = await freshStore()
    await store.checkManually()
    expect(store.status).toBe('error')
    expect(store.lastError).toBe('rate_limit')
  })

  it('setFrequency updates state and persists via electron', async () => {
    const e = makeElectron()
    ;(window as any).electron = e
    const store = await freshStore()
    store.setFrequency('never')
    expect(store.frequency).toBe('never')
    expect(e.setUpdateFrequency).toHaveBeenCalledWith('never')
  })

  it("download('only') sets pendingInstaller and closes the modal", async () => {
    const e = makeElectron()
    ;(window as any).electron = e
    const store = await freshStore()
    store.modalVisible = true
    await store.download('only')
    expect(e.downloadUpdate).toHaveBeenCalledOnce()
    expect(e.runInstaller).not.toHaveBeenCalled()
    expect(store.pendingInstaller).toContain('MediaTranX-Setup-1.6.0-full-win.exe')
    expect(store.modalVisible).toBe(false)
    expect(store.downloading).toBe(false)
  })

  it("download('install') downloads then runs the installer", async () => {
    const e = makeElectron()
    ;(window as any).electron = e
    const store = await freshStore()
    await store.download('install')
    expect(e.downloadUpdate).toHaveBeenCalledOnce()
    expect(e.runInstaller).toHaveBeenCalledOnce()
  })

  it('download surfaces an error without running installer', async () => {
    const e = makeElectron({ downloadUpdate: vi.fn(async () => ({ error: 'network' })) })
    ;(window as any).electron = e
    const store = await freshStore()
    await store.download('install')
    expect(store.lastError).toBe('network')
    expect(e.runInstaller).not.toHaveBeenCalled()
    expect(store.downloading).toBe(false)
  })

  it('installNow calls runInstaller', async () => {
    const e = makeElectron()
    ;(window as any).electron = e
    const store = await freshStore()
    await store.installNow()
    expect(e.runInstaller).toHaveBeenCalledOnce()
  })

  it('no window.electron → all actions are safe no-ops', async () => {
    const store = await freshStore()
    await store.init()
    await store.checkManually()
    store.setFrequency('weekly')
    await store.download('install')
    await store.installNow()
    // nothing threw; status untouched from idle
    expect(store.status).toBe('idle')
  })

  it('applyResult via checkManually records channel and suffixed latest', async () => {
    ;(window as any).electron = makeElectron({
      checkForUpdates: vi.fn(async () => ({
        status: 'update-available',
        channel: 'dev',
        current: '1.5.2',
        latest: '1.6.0-dev.4',
        asset: { name: 'x', size: 1, browser_download_url: 'u' },
      })),
    })
    const s = await freshStore()
    await s.checkManually()
    expect(s.channel).toBe('dev')
    expect(s.latest).toBe('1.6.0-dev.4') // 後綴保留（MAJOR-1 驗收）
  })
})

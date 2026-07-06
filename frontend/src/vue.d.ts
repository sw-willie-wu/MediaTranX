/* eslint-disable @typescript-eslint/no-explicit-any */
declare module '*.vue' {
    import { DefineComponent } from 'vue'
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    const component: DefineComponent<{}, {}, any>
    export default component
  }
/* eslint-enable @typescript-eslint/no-explicit-any */

interface SaveFileDialogOptions {
  title?: string
  defaultPath?: string
  filters?: { name: string; extensions: string[] }[]
}

interface Window {
  electron?: {
    minimize: () => void
    maximize: () => void
    close: () => void
    isMaximized: () => Promise<boolean>
    onMaximizeChange: (callback: (value: boolean) => void) => void
    selectFolder: () => Promise<string | null>
    saveFileDialog: (options: SaveFileDialogOptions) => Promise<string | null>
    getFileSourceDir: (name: string, size: number, lastModified: number) => string | null
    downloadToPath: (url: string, destPath: string, srcPath?: string) => Promise<void>
    showItemInFolder: (filePath: string) => void
    openPath: (filePath: string) => Promise<string>
    openExternal?: (url: string) => Promise<void>
    fileExists: (filePath: string) => Promise<boolean>
    readLocalFile: (filePath: string) => Promise<Uint8Array>
    restart: () => void
    appVersion?: string | null
    savePreference?: (key: string, value: unknown) => void
    // Software update
    checkForUpdates: () => Promise<UpdateCheckResult>
    downloadUpdate: () => Promise<{ path?: string; error?: string }>
    runInstaller: () => Promise<{ ok?: boolean; error?: string }>
    getUpdatePrefs: () => Promise<UpdatePrefs>
    setUpdateFrequency: (freq: string) => void
    onUpdateDownloadProgress: (cb: (p: UpdateDownloadProgress) => void) => void
    onUpdateAvailable: (cb: (r: UpdateCheckResult) => void) => void
  }
}

type UpdateFrequency = 'startup' | 'weekly' | 'monthly' | 'manual'

interface UpdateAsset {
  name: string
  size: number
  browser_download_url: string
}

interface UpdateCheckResult {
  status: 'up-to-date' | 'update-available' | 'error'
  channel?: 'dev' | 'stable'
  current?: string
  latest?: string
  asset?: UpdateAsset | null
  error?: string
}

interface UpdatePrefs {
  frequency: UpdateFrequency
  lastUpdateCheck?: number
  pendingInstaller: string | null
}

interface UpdateDownloadProgress {
  percent: number
  received: number
  total: number
}
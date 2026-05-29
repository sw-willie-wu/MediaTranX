/**
 * 下載後端產出檔案到本機
 * 透過 Electron saveFileDialog 讓用戶選擇儲存路徑，再由 IPC 寫入磁碟
 */
import { useToast } from './useToast'
import { getApiBase, apiFetch } from './useApi'
import { createLogger } from '@/utils/logger'
import i18n from '@/i18n'
import type { MediaEntry } from '@/composables/useMediaCollection'

const toast = useToast()
const log = createLogger('FileDownload')
const { t } = i18n.global

/**
 * Return a filename that doesn't collide with:
 *   - existing files in `dir` (checked via Electron IPC)
 *   - names already chosen in this batch (`reserved`)
 *
 * Windows-style parenthesis suffix: `foo.png` -> `foo (1).png` -> `foo (2).png`.
 * Caller must add the returned name to `reserved` before the next call.
 */
async function resolveUniqueFilename(
  dir: string,
  filename: string,
  reserved: Set<string>,
): Promise<string> {
  const fileExists = window.electron?.fileExists
  if (!fileExists) {
    // No IPC (dev-only fallback) — just use the requested name.
    return filename
  }
  // Last-dot split (Windows Explorer semantics): foo.tar.gz -> foo.tar (1).gz
  const dot = filename.lastIndexOf('.')
  const base = dot > 0 ? filename.slice(0, dot) : filename
  const ext = dot > 0 ? filename.slice(dot) : ''
  let candidate = filename
  for (let n = 0; n < 1000; n++) {
    if (n > 0) candidate = `${base} (${n})${ext}`
    if (reserved.has(candidate)) continue
    const exists = await fileExists(`${dir}/${candidate}`)
    if (!exists) return candidate
  }
  throw new Error(`resolveUniqueFilename: exhausted 1000 attempts for ${filename}`)
}

/**
 * For each selected entry, resolve its latest output (or original if no
 * history) plus the backend disk path for fast fs.copyFileSync. Skips entries
 * that are processing or have no fileId.
 */
export async function collectLatestOutputs(
  ids: string[],
  entries: Map<string, MediaEntry>,
): Promise<{ fileId: string; filename: string; srcPath?: string }[]> {
  const resolved = await Promise.all(
    ids.map(async (id) => {
      const e = entries.get(id)
      if (!e || e.status === 'processing') return null
      const latest = e.historyStack.at(-1)
      const fileId = latest ? latest.fileId : e.fileId
      if (!fileId) return null
      const filename = latest ? latest.outputFilename : e.fileName
      let srcPath: string | undefined
      try {
        const res = await apiFetch(`/files/${fileId}`)
        if (res.ok) srcPath = (await res.json()).file_path
      } catch {}
      return { fileId, filename, srcPath }
    }),
  )
  return resolved.filter((x): x is NonNullable<typeof x> => x !== null)
}

export function useFileDownload() {
  async function downloadFile(fileId: string, defaultName: string, defaultDir?: string): Promise<string | null> {
    if (!window.electron?.saveFileDialog) return null

    const ext = defaultName.split('.').pop() ?? ''
    const filters = ext
      ? [{ name: ext.toUpperCase(), extensions: [ext] }, { name: t('common.all_files'), extensions: ['*'] }]
      : [{ name: t('common.all_files'), extensions: ['*'] }]

    // 組合預設儲存路徑：若有原始目錄則用，否則只帶檔名讓系統決定位置
    const defaultPath = defaultDir
      ? `${defaultDir.replace(/\\/g, '/')}/${defaultName}`
      : defaultName

    const destPath = await window.electron.saveFileDialog({
      title: t('common.save'),
      defaultPath,
      filters,
    })
    if (!destPath) return null

    // Try to get the file's disk path for direct copy (skip HTTP)
    let srcPath: string | undefined
    try {
      const infoRes = await fetch(`${getApiBase()}/files/${fileId}`)
      if (infoRes.ok) {
        const info = await infoRes.json()
        srcPath = info.file_path
      }
    } catch {}

    log.info('downloadFile', { fileId, destPath, srcPath })
    try {
      await window.electron.downloadToPath(
        `${getApiBase()}/files/${fileId}/download`,
        destPath,
        srcPath,
      )
      log.info('downloadFile done', { fileId, destPath })
      toast.show(t('toast.saved'), {
        type: 'success',
        icon: 'bi-check-circle',
      })
      return destPath
    } catch (e) {
      log.error('downloadFile failed', { fileId, destPath, error: e })
      toast.show(t('toast.save_failed'), { type: 'error', icon: 'bi-x-circle' })
      return null
    }
  }

  async function downloadBatch(
    entries: { fileId: string; filename: string; srcPath?: string }[],
    onEach?: (fileId: string, destPath: string) => void,
  ): Promise<Map<string, string>> {
    /** Returns a map of fileId → savedPath for successfully written files.
     *  `onEach` is invoked per-file as soon as that file completes writing. */
    const saved = new Map<string, string>()
    if (!window.electron?.selectFolder) return saved

    const destDir = await window.electron.selectFolder()
    if (!destDir) return saved

    const normalizedDir = destDir.replace(/\\/g, '/')

    // Resolve collision-free filenames before writing. Must be sequential so
    // two entries can't both claim "foo (1).png".
    // This runs outside the batch try/catch: if resolution throws (exhausted
    // 1000 attempts or IPC failure) we want the error to surface distinctly
    // rather than collapse into a generic "batch save failed" toast.
    const reserved = new Set<string>()
    const prepared: { fileId: string; filename: string; srcPath?: string }[] = []
    try {
      for (const e of entries) {
        const finalName = await resolveUniqueFilename(normalizedDir, e.filename, reserved)
        reserved.add(finalName)
        prepared.push({ ...e, filename: finalName })
      }
    } catch (e) {
      log.error('downloadBatch resolve failed', { destDir, error: e })
      throw e
    }

    log.info('downloadBatch', { destDir, count: entries.length })
    try {
      await Promise.all(
        prepared.map(async ({ fileId, filename, srcPath }) => {
          const url = `${getApiBase()}/files/${fileId}/download`
          const destPath = `${normalizedDir}/${filename}`
          try {
            await window.electron!.downloadToPath(url, destPath, srcPath)
            saved.set(fileId, destPath)
            onEach?.(fileId, destPath)
          } catch (e) {
            log.warn('batch entry failed', { fileId, destPath, e })
          }
        }),
      )
      log.info('downloadBatch done', { saved: saved.size, total: entries.length })
      toast.show(t('toast.batch_saved', { count: saved.size }), {
        type: 'success',
        icon: 'bi-check-circle',
      })
    } catch (e) {
      log.error('downloadBatch failed', { error: e })
      toast.show(t('toast.batch_save_failed'), { type: 'error', icon: 'bi-x-circle' })
    }
    return saved
  }

  return { downloadFile, downloadBatch }
}

/**
 * Results drawer 狀態管理
 *
 * 追蹤後端 output 檔案（以 metadata.show_in_results=true 為準），
 * 並在任務完成時自動收集新產生的輸出。
 */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Router } from 'vue-router'
import { apiFetch } from '@/composables/useApi'
import { useTaskStore } from '@/stores/tasks'
import { useFilesStore } from '@/stores/files'
import { detectTypeByName, getToolPath, type ToolType } from '@/utils/mediaType'
import { createLogger } from '@/utils/logger'

const log = createLogger('ResultsStore')

export interface ResultEntry {
  fileId: string
  filename: string
  filePath: string
  originalFilename?: string
  fileSize: number
  mimeType: string
  createdAt: string
  toolId: string
  sourceFileId?: string
  /** Last-saved destination path on user's disk, set after Save / batch Save */
  savedPath?: string
}

interface ApiFileInfo {
  file_id: string
  filename: string
  file_path: string
  original_filename: string
  file_size: number
  mime_type: string
  created_at: string
  metadata?: {
    tool_id?: string
    source_file_id?: string
    show_in_results?: boolean
    saved_path?: string
  }
}

export const useResultsStore = defineStore('results', () => {
  const results = ref<ResultEntry[]>([])
  const unreadCount = ref(0)
  const selectedIds = ref<Set<string>>(new Set())
  const savingIds = ref<Set<string>>(new Set())
  const groupMode = ref<'time' | 'tool'>('time')
  const loaded = ref(false)

  // Backwards compat boolean (some templates may still use hasUnread)
  const hasUnread = computed(() => unreadCount.value > 0)

  const sortedResults = computed(() =>
    [...results.value].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    ),
  )

  const groupedByTool = computed(() => {
    const map = new Map<string, ResultEntry[]>()
    for (const r of sortedResults.value) {
      const key = r.toolId || 'unknown'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return Array.from(map.entries())
  })

  const allSelected = computed(
    () => results.value.length > 0 && selectedIds.value.size === results.value.length,
  )
  const someSelected = computed(
    () => selectedIds.value.size > 0 && selectedIds.value.size < results.value.length,
  )

  const selectedCategory = computed<ToolType | 'mixed' | null>(() => {
    if (selectedIds.value.size === 0) return null
    const cats = new Set<ToolType | null>()
    for (const id of selectedIds.value) {
      const r = results.value.find((x) => x.fileId === id)
      if (!r) continue
      cats.add(detectTypeByName(r.filename, r.mimeType))
    }
    cats.delete(null)
    if (cats.size === 0) return null
    if (cats.size === 1) return [...cats][0] as ToolType
    return 'mixed'
  })

  function fromApi(f: ApiFileInfo): ResultEntry {
    return {
      fileId: f.file_id,
      filename: f.filename,
      filePath: f.file_path,
      originalFilename: f.original_filename,
      fileSize: f.file_size,
      mimeType: f.mime_type,
      createdAt: f.created_at,
      toolId: f.metadata?.tool_id ?? 'unknown',
      sourceFileId: f.metadata?.source_file_id,
      savedPath: f.metadata?.saved_path,
    }
  }

  /** Persist saved path to backend sidecar so it survives restart. */
  async function persistSavedPath(fileId: string, destPath: string): Promise<void> {
    try {
      const res = await apiFetch(`/files/${fileId}/saved-path`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ saved_path: destPath }),
      })
      if (!res.ok) log.warn('persistSavedPath non-2xx', { fileId, status: res.status })
    } catch (e) {
      log.warn('persistSavedPath failed', { fileId, e })
    }
  }

  async function loadInitial() {
    if (loaded.value) return
    try {
      const res = await apiFetch('/files?kind=output')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: ApiFileInfo[] = await res.json()
      results.value = data.map(fromApi)
      loaded.value = true
      log.info('initial load', { count: results.value.length })
    } catch (e) {
      log.error('loadInitial failed', e)
    }
  }

  async function addFromTask(
    taskResult: unknown,
    taskType: string,
  ) {
    const r = (taskResult ?? {}) as Record<string, unknown>
    const fileIds: string[] = []
    if (typeof r.output_file_id === 'string') fileIds.push(r.output_file_id)
    if (Array.isArray(r.output_files)) {
      for (const f of r.output_files as Array<{ file_id?: string }>) {
        if (f?.file_id && !fileIds.includes(f.file_id)) fileIds.push(f.file_id)
      }
    }
    for (const [k, v] of Object.entries(r)) {
      if (k.endsWith('_file_id') && typeof v === 'string' && !fileIds.includes(v)) {
        fileIds.push(v)
      }
    }

    for (const fileId of fileIds) {
      if (results.value.some((r) => r.fileId === fileId)) continue
      try {
        const res = await apiFetch(`/files/${fileId}`)
        if (!res.ok) continue
        const info: ApiFileInfo = await res.json()
        if (info.metadata?.show_in_results !== true) continue
        if (results.value.some((r) => r.fileId === fileId)) continue
        results.value.push(fromApi(info))
        unreadCount.value += 1
        log.info('addFromTask pushed', { fileId, taskType })
      } catch (e) {
        log.warn('addFromTask fetch failed', e)
      }
    }
  }

  async function saveOne(fileId: string): Promise<void> {
    const r = results.value.find(x => x.fileId === fileId)
    if (!r) return
    savingIds.value.add(fileId)
    try {
      const { useFileDownload } = await import('@/composables/useFileDownload')
      const { downloadFile } = useFileDownload()
      const destPath = await downloadFile(r.fileId, r.filename)
      if (destPath) {
        const idx = results.value.findIndex((x) => x.fileId === fileId)
        if (idx >= 0) {
          results.value[idx] = { ...results.value[idx], savedPath: destPath }
        }
        await persistSavedPath(fileId, destPath)
      }
    } finally {
      savingIds.value.delete(fileId)
      savingIds.value = new Set(savingIds.value) // trigger reactivity on Set
    }
  }

  function browseSaved(fileId: string): void {
    const r = results.value.find(x => x.fileId === fileId)
    if (!r?.savedPath) return
    window.electron?.showItemInFolder(r.savedPath)
  }

  async function previewOne(fileId: string): Promise<void> {
    const r = results.value.find(x => x.fileId === fileId)
    if (!r) return
    try {
      // Look up the backend file path then open with OS default app
      const res = await apiFetch(`/files/${fileId}`)
      if (!res.ok) return
      const info: ApiFileInfo & { file_path?: string } = await res.json()
      const filePath = (info as { file_path?: string }).file_path
      if (filePath && window.electron?.openPath) {
        await window.electron.openPath(filePath)
      }
    } catch (e) {
      log.warn('previewOne failed', e)
    }
  }

  async function removeOne(fileId: string): Promise<void> {
    try {
      await apiFetch(`/files/${fileId}`, { method: 'DELETE' })
      results.value = results.value.filter((r) => r.fileId !== fileId)
      selectedIds.value.delete(fileId)
    } catch (e) {
      log.error('removeOne failed', e)
    }
  }

  async function saveBatch(ids: string[]): Promise<void> {
    const { useFileDownload } = await import('@/composables/useFileDownload')
    const { downloadBatch } = useFileDownload()
    const entries = ids
      .map((id) => results.value.find((r) => r.fileId === id))
      .filter((r): r is ResultEntry => !!r)
      .map((r) => ({ fileId: r.fileId, filename: r.filename, srcPath: r.filePath }))
    if (entries.length === 0) return

    // Mark all selected as saving (triggers Set reactivity via replacement)
    const next = new Set(savingIds.value)
    for (const e of entries) next.add(e.fileId)
    savingIds.value = next

    try {
      // As each file finishes, update that entry's savedPath and clear its
      // saving flag immediately (per-card "saving → browse" transition).
      await downloadBatch(entries, (fileId, destPath) => {
        const idx = results.value.findIndex((x) => x.fileId === fileId)
        if (idx >= 0) {
          results.value[idx] = { ...results.value[idx], savedPath: destPath }
        }
        savingIds.value = new Set([...savingIds.value].filter((id) => id !== fileId))
        persistSavedPath(fileId, destPath)
      })
    } finally {
      // Safety net: clear any savingIds still flagged (e.g. failed entries)
      const cleanup = new Set(savingIds.value)
      let changed = false
      for (const e of entries) {
        if (cleanup.delete(e.fileId)) changed = true
      }
      if (changed) savingIds.value = cleanup
    }
  }

  async function deleteBatch(ids: string[]): Promise<void> {
    await Promise.all(ids.map((id) => removeOne(id)))
  }

  /**
   * Stage a result file by reference (no blob download) and route to the
   * matching tool. If already on that route, dispatch a window event so the
   * active Workspace composable can pick up the pending refs immediately.
   */
  async function openInTool(
    fileId: string,
    router: Router,
    currentRoute: string,
  ): Promise<void> {
    const r = results.value.find((x) => x.fileId === fileId)
    if (!r) return

    const targetType = detectTypeByName(r.filename, r.mimeType)
    if (!targetType) {
      log.warn('openInTool: unknown type', { fileId, filename: r.filename })
      return
    }

    useFilesStore().setPendingResults([
      { fileId: r.fileId, filename: r.filename, fileSize: r.fileSize, mimeType: r.mimeType },
    ])

    const targetPath = getToolPath(targetType)
    if (currentRoute !== targetPath) {
      await router.push(targetPath)
    } else {
      window.dispatchEvent(new CustomEvent('pending-results-ready'))
    }
  }

  /**
   * Batch counterpart of openInTool. Stages all selected files by reference
   * (no blob download), then routes to the matching tool. All ids must resolve
   * to the same target tool — caller (BatchBar) ensures this via canOpenInTool guard.
   */
  async function openManyInTool(
    ids: string[],
    router: Router,
    currentRoute: string,
  ): Promise<void> {
    if (ids.length === 0) return

    const entries = ids
      .map((id) => results.value.find((r) => r.fileId === id))
      .filter((r): r is ResultEntry => !!r)
    if (entries.length === 0) return

    let targetType: ToolType | null = null
    const refs: { fileId: string; filename: string; fileSize: number; mimeType: string }[] = []
    for (const e of entries) {
      const tt = detectTypeByName(e.filename, e.mimeType)
      if (tt === null) {
        log.warn('openManyInTool: unknown type, skipped', { fileId: e.fileId })
        continue
      }
      if (targetType === null) targetType = tt
      else if (targetType !== tt) {
        log.error('openManyInTool: mixed types — caller should guard', { ids })
        return
      }
      refs.push({ fileId: e.fileId, filename: e.filename, fileSize: e.fileSize, mimeType: e.mimeType })
    }
    if (!targetType || refs.length === 0) return

    useFilesStore().setPendingResults(refs)

    const targetPath = getToolPath(targetType)
    if (currentRoute !== targetPath) {
      await router.push(targetPath)
    } else {
      window.dispatchEvent(new CustomEvent('pending-results-ready'))
    }
  }

  async function clearAll(): Promise<void> {
    const ids = results.value.map((r) => r.fileId)
    await Promise.all(ids.map((id) => apiFetch(`/files/${id}`, { method: 'DELETE' })))
    resetLocal()
  }

  /** Clear only local UI state — caller is responsible for backend cleanup
   *  (used by Settings "clear temp" which uses the bulk /files/cleanup endpoint). */
  function resetLocal(): void {
    results.value = []
    selectedIds.value.clear()
    savingIds.value = new Set()
    unreadCount.value = 0
  }

  function toggleSelect(fileId: string) {
    if (selectedIds.value.has(fileId)) selectedIds.value.delete(fileId)
    else selectedIds.value.add(fileId)
  }

  function toggleSelectAll() {
    if (allSelected.value) selectedIds.value.clear()
    else selectedIds.value = new Set(results.value.map((r) => r.fileId))
  }

  function clearSelection() {
    selectedIds.value.clear()
  }

  function markRead() {
    unreadCount.value = 0
  }

  let autoCollectStarted = false
  function startAutoCollect() {
    if (autoCollectStarted) return
    autoCollectStarted = true
    const taskStore = useTaskStore()
    const seen = new Set<string>()
    watch(
      () => Array.from(taskStore.tasks.values()),
      (tasks) => {
        for (const t of tasks) {
          if (t.status !== 'completed') continue
          if (seen.has(t.taskId)) continue
          seen.add(t.taskId)
          if (!t.result) continue
          addFromTask(t.result, t.taskType)
        }
      },
      { deep: true },
    )
  }

  return {
    results,
    sortedResults,
    groupedByTool,
    groupMode,
    selectedIds,
    savingIds,
    hasUnread,
    unreadCount,
    allSelected,
    someSelected,
    selectedCategory,
    loadInitial,
    addFromTask,
    saveOne,
    browseSaved,
    previewOne,
    removeOne,
    saveBatch,
    deleteBatch,
    openInTool,
    openManyInTool,
    clearAll,
    resetLocal,
    toggleSelect,
    toggleSelectAll,
    clearSelection,
    markRead,
    startAutoCollect,
  }
})

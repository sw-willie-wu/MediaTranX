import { ref, computed, watch } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { useToast } from '@/composables/useToast'
import { getApiBase } from '@/composables/useApi'
import { createLogger } from '@/utils/logger'
import i18n from '@/i18n'

const log = createLogger('MediaCollection')
const { t } = i18n.global

export interface HistoryEntry {
  fileId: string
  previewUrl: string
  outputFilename: string
  taskType?: string
  meta?: Record<string, unknown>
}

export interface MediaEntry {
  id: string
  file: File
  fileId: string | null
  sourceDir?: string
  previewUrl: string       // full-res blob URL of the original file
  thumbnailUrl: string
  status: 'idle' | 'uploading' | 'processing' | 'done'
  progress: number
  historyStack: HistoryEntry[]
  redoStack: HistoryEntry[]
  currentTaskId: string | null
}

export interface MediaCollectionOptions {
  /** Return false to skip adding this result to historyStack (e.g. text-only results like OCR) */
  shouldAddToHistory?: (result: Record<string, unknown>, taskType: string) => boolean
}

export function useMediaCollection(options?: MediaCollectionOptions) {
  const taskStore = useTaskStore()
  const toast = useToast()

  // --- State ---
  const entries = ref<Map<string, MediaEntry>>(new Map())
  const activeId = ref<string | null>(null)
  const selectedIds = ref<Set<string>>(new Set())

  // Internal map: taskId → entryId
  const taskEntryMap = new Map<string, string>()

  // --- Computed ---
  const activeEntry = computed<MediaEntry | null>(
    () => (activeId.value ? (entries.value.get(activeId.value) ?? null) : null)
  )

  const isMultiSelect = computed<boolean>(() => selectedIds.value.size > 1)

  const hasEntries = computed<boolean>(() => entries.value.size > 0)

  const entriesList = computed<MediaEntry[]>(() => Array.from(entries.value.values()))

  // --- Methods ---

  async function addEntry(
    file: File,
    srcDir?: string,
    generateThumbnail?: (file: File, previewUrl: string) => Promise<string>,
  ): Promise<string> {
    const id = crypto.randomUUID()
    const previewUrl = URL.createObjectURL(file)
    const thumbnailUrl = generateThumbnail
      ? await generateThumbnail(file, previewUrl)
      : previewUrl

    const entry: MediaEntry = {
      id,
      file,
      fileId: null,
      sourceDir: srcDir,
      previewUrl,
      thumbnailUrl,
      status: 'uploading',
      progress: 0,
      historyStack: [],
      redoStack: [],
      currentTaskId: null,
    }

    entries.value.set(id, entry)
    activeId.value = id
    selectedIds.value = new Set()
    log.info('addEntry', { id, fileName: file.name, hasSrcDir: !!srcDir })

    return id
  }

  function removeEntry(id: string): void {
    const entry = entries.value.get(id)
    if (!entry) return
    log.info('removeEntry', { id, fileName: entry.file.name })

    URL.revokeObjectURL(entry.previewUrl)
    if (entry.thumbnailUrl !== entry.previewUrl && entry.thumbnailUrl.startsWith('blob:')) {
      URL.revokeObjectURL(entry.thumbnailUrl)
    }

    entries.value.delete(id)

    if (activeId.value === id) {
      // Select next or previous entry after removal
      const list = Array.from(entries.value.keys())
      activeId.value = list.length > 0 ? list[0] : null
    }

    if (selectedIds.value.has(id)) {
      const next = new Set(selectedIds.value)
      next.delete(id)
      selectedIds.value = next
    }
  }

  function removeEntries(ids: string[]): void {
    for (const id of ids) {
      removeEntry(id)
    }
  }

  function removeAllEntries(): void {
    for (const entry of entries.value.values()) {
      URL.revokeObjectURL(entry.previewUrl)
      if (entry.thumbnailUrl !== entry.previewUrl && entry.thumbnailUrl.startsWith('blob:')) {
        URL.revokeObjectURL(entry.thumbnailUrl)
      }
    }
    entries.value = new Map()
    activeId.value = null
    selectedIds.value = new Set()
  }

  function selectEntry(id: string, ctrlKey: boolean): void {
    const entry = entries.value.get(id)
    if (!entry) return

    // Processing entries: allow viewing (single click) but not multi-select
    if (entry.status === 'processing' && ctrlKey) return

    if (ctrlKey) {
      const next = new Set(selectedIds.value)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      selectedIds.value = next
      if (selectedIds.value.size === 0) {
        activeId.value = null
      }
    } else {
      selectedIds.value = new Set([id])
      activeId.value = id
    }
  }

  function clearSelection(): void {
    selectedIds.value = new Set(activeId.value ? [activeId.value] : [])
  }

  function selectAll(): void {
    const ids = new Set<string>()
    for (const [id, entry] of entries.value) {
      if (entry.status !== 'processing') ids.add(id)
    }
    selectedIds.value = ids
  }

  function updateEntry(id: string, patch: Partial<MediaEntry>): void {
    const entry = entries.value.get(id)
    if (!entry) return
    entries.value.set(id, { ...entry, ...patch })
  }

  function registerTask(taskId: string, entryId: string): void {
    taskEntryMap.set(taskId, entryId)
    log.info('registerTask', { taskId, entryId })
  }

  // --- Task completion watcher ---
  watch(
    () => taskStore.tasks,
    (tasks) => {
      for (const [taskId, task] of tasks.entries()) {
        const entryId = taskEntryMap.get(taskId)
        if (!entryId) continue

        if (task.status === 'completed' && task.result) {
          const r = task.result as Record<string, unknown>
          const outputFileId = r.output_file_id as string | undefined
          const outputFilename = r.output_filename as string | undefined
          if (outputFileId) {
            const entry = entries.value.get(entryId)
            if (!entry) continue

            // Allow consumer to skip historyStack for non-image results (e.g. OCR text).
            // Keep currentTaskId so the consumer's watcher can still process it.
            if (options?.shouldAddToHistory && !options.shouldAddToHistory(r, task.taskType)) {
              log.info('task completed (skipped history)', { taskId, entryId, outputFileId })
              updateEntry(entryId, { status: 'done' })
              taskEntryMap.delete(taskId)
              continue
            }

            const previewUrl = `${getApiBase()}/files/${outputFileId}/download`

            // Collect extra metadata (e.g. crop_x, crop_y) excluding standard fields
            const { output_file_id: _, output_filename: __, ...meta } = r

            const historyEntry: HistoryEntry = {
              fileId: outputFileId,
              previewUrl,
              outputFilename: outputFilename ?? entry.file.name,
              taskType: task.taskType,
              meta: Object.keys(meta).length > 0 ? meta : undefined,
            }

            log.info('task completed → history push', {
              taskId, entryId, outputFileId,
              historyDepth: entry.historyStack.length + 1,
              taskType: task.taskType,
            })

            // Always append — user uses "go back" to undo
            const newStack = [...entry.historyStack, historyEntry]

            updateEntry(entryId, {
              historyStack: newStack,
              redoStack: [],  // 新操作清空 redo
              status: 'done',
              currentTaskId: null,
            })
            taskEntryMap.delete(taskId)
          }
        } else if (task.status === 'processing') {
          const entry = entries.value.get(entryId)
          if (!entry) continue
          if (entry.progress !== task.progress) {
            updateEntry(entryId, { progress: task.progress })
          }
        } else if (task.status === 'failed' || task.status === 'cancelled') {
          const entry = entries.value.get(entryId)
          if (!entry) continue
          if (task.status === 'failed' && task.error) {
            toast.show(t('toast.task_failed', { label: task.label ?? task.taskType, error: task.error }), { type: 'error', icon: 'bi-x-circle' })
          }
          log.warn(`task ${task.status}`, { taskId, entryId, error: task.error })
          updateEntry(entryId, {
            status: 'idle',
            currentTaskId: null,
          })
          taskEntryMap.delete(taskId)
        }
      }
    },
    { deep: true },
  )

  return {
    // State
    entries,
    activeId,
    selectedIds,
    // Computed
    activeEntry,
    isMultiSelect,
    hasEntries,
    entriesList,
    // Methods
    addEntry,
    removeEntry,
    removeEntries,
    removeAllEntries,
    selectEntry,
    clearSelection,
    selectAll,
    updateEntry,
    registerTask,
  }
}

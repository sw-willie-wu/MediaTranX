import { ref, computed, watch } from 'vue'
import { useTaskStore } from '@/stores/tasks'
import { getApiBase } from '@/composables/useApi'

export interface HistoryEntry {
  fileId: string
  previewUrl: string
  outputFilename: string
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
  currentTaskId: string | null
}

export function useMediaCollection() {
  const taskStore = useTaskStore()

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
      currentTaskId: null,
    }

    entries.value.set(id, entry)
    activeId.value = id
    selectedIds.value = new Set()

    return id
  }

  function removeEntry(id: string): void {
    const entry = entries.value.get(id)
    if (!entry) return

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

    // Processing entries cannot be selected for new operations
    if (entry.status === 'processing') return

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

  function updateEntry(id: string, patch: Partial<MediaEntry>): void {
    const entry = entries.value.get(id)
    if (!entry) return
    entries.value.set(id, { ...entry, ...patch })
  }

  function registerTask(taskId: string, entryId: string): void {
    taskEntryMap.set(taskId, entryId)
  }

  // --- Task completion watcher ---
  watch(
    () => taskStore.tasks,
    (tasks) => {
      for (const [taskId, task] of tasks.entries()) {
        const entryId = taskEntryMap.get(taskId)
        if (!entryId) continue

        if (task.status === 'completed' && task.result) {
          const r = task.result as { output_file_id?: string; output_filename?: string }
          if (r.output_file_id) {
            const previewUrl = `${getApiBase()}/files/${r.output_file_id}/download`
            const entry = entries.value.get(entryId)
            if (!entry) continue

            const historyEntry: HistoryEntry = {
              fileId: r.output_file_id,
              previewUrl,
              outputFilename: r.output_filename ?? entry.file.name,
            }

            updateEntry(entryId, {
              historyStack: [...entry.historyStack, historyEntry],
              status: 'done',
              currentTaskId: null,
            })
            taskEntryMap.delete(taskId)
          }
        } else if (task.status === 'failed') {
          const entry = entries.value.get(entryId)
          if (!entry) continue
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
    removeAllEntries,
    selectEntry,
    clearSelection,
    updateEntry,
    registerTask,
  }
}

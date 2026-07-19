/**
 * View Registry  (§6.5b)
 *
 * Plain module-level Map (NOT Pinia) keyed by viewId.
 * Views register themselves in onMounted / onUnmounted.
 * Agent tools call viewRegistry.get(viewId)?.setCurrentFunction(id).
 */
import type { Ref } from 'vue'

export interface ViewActiveFile {
  id: string
  name: string
  kind: string
}

export interface ViewHandle {
  /** The currently-active function/tab ID within this view */
  currentFunction: Ref<string>
  /** Switch to a different function/tab */
  setCurrentFunction: (id: string) => void
  /**
   * Bug #22: return the list of valid subfunction IDs for this view.
   * Optional — views that don't declare it are treated as "allow any".
   */
  validSubfunctions?: () => string[]
  /**
   * 跨 domain 檔案上下文污染修復（v1.7.1）：本 view 當前作用檔案（歷史最新結果檔）。
   * agent state snapshot 的 active_file 唯一來源——與 current_position 保證同一個 domain，
   * 不再從全域 filesStore.currentFile 取（那個切 domain 從不重置、會殘留他 domain 檔）。
   * 未註冊（settings/pipeline 等無檔 view）或無檔時視為 null。
   */
  activeFile?: Ref<ViewActiveFile | null>
}

const _registry = new Map<string, ViewHandle>()

export const viewRegistry = {
  register(viewId: string, handle: ViewHandle): void {
    _registry.set(viewId, handle)
  },

  unregister(viewId: string): void {
    _registry.delete(viewId)
  },

  get(viewId: string): ViewHandle | undefined {
    return _registry.get(viewId)
  },

  /** For tests — clear all entries between test cases */
  _clearAll(): void {
    _registry.clear()
  },
}

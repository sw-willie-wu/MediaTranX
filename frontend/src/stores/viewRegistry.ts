/**
 * View Registry  (§6.5b)
 *
 * Plain module-level Map (NOT Pinia) keyed by viewId.
 * Views register themselves in onMounted / onUnmounted.
 * Agent tools call viewRegistry.get(viewId)?.setCurrentFunction(id).
 */
import type { Ref } from 'vue'

export interface ViewHandle {
  /** The currently-active function/tab ID within this view */
  currentFunction: Ref<string>
  /** Switch to a different function/tab */
  setCurrentFunction: (id: string) => void
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

import { ref, readonly, watchEffect, type WatchStopHandle } from 'vue'

/** 工具頁當前檔名（由各 View 設定，Titlebar 讀取） */
const activeFileName = ref('')

/** Titlebar fixed actions — undo/redo/save-as */
const _canUndo = ref(false)
const _canRedo = ref(false)
const _canSave = ref(false)
const _canSaveAs = ref(false)
let _onUndo: (() => void) | null = null
let _onRedo: (() => void) | null = null
let _onSave: (() => void) | null = null
let _onSaveAs: (() => void) | null = null
let _stopWatch: WatchStopHandle | null = null

/** Extra actions — 各工具頁動態註冊的額外按鈕 */
export interface TitlebarExtraAction {
  id: string
  icon: string
  tooltip: string
  active?: boolean
  disabled?: boolean
  onClick: () => void
}

const _extraActions = ref<TitlebarExtraAction[]>([])

export function useTitlebar() {
  function setFileName(name: string) {
    activeFileName.value = name
  }

  function clearFileName() {
    activeFileName.value = ''
  }

  /** 工具頁呼叫：註冊 undo/redo/saveAs handler，內部用 watchEffect 自動追蹤狀態 */
  function registerActions(actions: {
    canUndo: () => boolean
    canRedo: () => boolean
    canSave?: () => boolean
    canSaveAs: () => boolean
    onUndo: () => void
    onRedo: () => void
    onSave?: () => void
    onSaveAs: () => void
  }) {
    _onUndo = actions.onUndo
    _onRedo = actions.onRedo
    _onSave = actions.onSave ?? null
    _onSaveAs = actions.onSaveAs
    _stopWatch?.()
    _stopWatch = watchEffect(() => {
      _canUndo.value = actions.canUndo()
      _canRedo.value = actions.canRedo()
      _canSave.value = actions.canSave?.() ?? false
      _canSaveAs.value = actions.canSaveAs()
    })
  }

  function clearActions() {
    _stopWatch?.()
    _stopWatch = null
    _canUndo.value = false
    _canRedo.value = false
    _canSave.value = false
    _canSaveAs.value = false
    _onUndo = null
    _onRedo = null
    _onSave = null
    _onSaveAs = null
  }

  function undo() { _onUndo?.() }
  function redo() { _onRedo?.() }
  function save() { _onSave?.() }
  function saveAs() { _onSaveAs?.() }

  function setExtraActions(actions: TitlebarExtraAction[]) {
    _extraActions.value = actions
  }

  function clearExtraActions() {
    _extraActions.value = []
  }

  return {
    activeFileName,
    setFileName,
    clearFileName,
    // Fixed actions state
    canUndo: readonly(_canUndo),
    canRedo: readonly(_canRedo),
    canSave: readonly(_canSave),
    canSaveAs: readonly(_canSaveAs),
    undo,
    redo,
    save,
    saveAs,
    // Extra actions
    extraActions: readonly(_extraActions),
    setExtraActions,
    clearExtraActions,
    // Registration
    registerActions,
    clearActions,
  }
}

import { ref, onMounted, onUnmounted, type Ref } from 'vue'

export interface MidiKeyboardActions {
  deleteSelection: () => void
  undo: () => void
  redo: () => void
  copy: () => void
  paste: () => void
  duplicate: () => void
  selectAll: () => void
  togglePlay: () => void
  nudgeLeft: () => void
  nudgeRight: () => void
  nudgeUp: () => void
  nudgeDown: () => void
  setToolSelect: () => void
  setToolDraw: () => void
  setToolErase: () => void
}

export function useMidiKeyboard(
  canvasRef: Ref<HTMLCanvasElement | null>,
  actions: MidiKeyboardActions,
) {
  const canvasHasFocus = ref(false)

  function onMouseDown(e: MouseEvent) {
    const canvas = canvasRef.value
    if (canvas && canvas.contains(e.target as Node)) {
      canvasHasFocus.value = true
      canvas.focus()
    } else {
      canvasHasFocus.value = false
    }
  }

  function onKeyDown(e: KeyboardEvent) {
    if (!canvasHasFocus.value) return

    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

    const ctrl = e.ctrlKey || e.metaKey
    const shift = e.shiftKey
    const key = e.key

    let handled = true

    if (key === 'Delete' || key === 'Backspace') {
      actions.deleteSelection()
    } else if (ctrl && !shift && key === 'z') {
      actions.undo()
    } else if (ctrl && key === 'y') {
      actions.redo()
    } else if (ctrl && shift && key === 'Z') {
      actions.redo()
    } else if (ctrl && key === 'c') {
      actions.copy()
    } else if (ctrl && key === 'v') {
      actions.paste()
    } else if (ctrl && key === 'd') {
      actions.duplicate()
    } else if (ctrl && key === 'a') {
      actions.selectAll()
    } else if (key === ' ') {
      actions.togglePlay()
    } else if (key === 'ArrowLeft') {
      actions.nudgeLeft()
    } else if (key === 'ArrowRight') {
      actions.nudgeRight()
    } else if (key === 'ArrowUp') {
      actions.nudgeUp()
    } else if (key === 'ArrowDown') {
      actions.nudgeDown()
    } else if (key === 'v' || key === '1') {
      actions.setToolSelect()
    } else if (key === 'b' || key === '2') {
      actions.setToolDraw()
    } else if (key === 'e' || key === '3') {
      actions.setToolErase()
    } else {
      handled = false
    }

    if (handled) {
      e.preventDefault()
      e.stopPropagation()
    }
  }

  onMounted(() => {
    document.addEventListener('mousedown', onMouseDown)
    window.addEventListener('keydown', onKeyDown)
  })

  onUnmounted(() => {
    document.removeEventListener('mousedown', onMouseDown)
    window.removeEventListener('keydown', onKeyDown)
  })

  return { canvasHasFocus }
}

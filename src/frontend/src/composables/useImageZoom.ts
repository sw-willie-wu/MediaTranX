import { ref, computed, onBeforeUnmount } from 'vue'

export function useImageZoom(
  imgRef: Readonly<{ value: HTMLImageElement | null }>,
  containerRef: Readonly<{ value: HTMLElement | null }>,
) {
  const zoomLevel = ref(1)
  const panX = ref(0)
  const panY = ref(0)
  const isDragging = ref(false)
  const fitPercent = ref(100)

  let _dragStartX = 0
  let _dragStartY = 0
  let _panStartX = 0
  let _panStartY = 0

  function reset() {
    zoomLevel.value = 1
    panX.value = 0
    panY.value = 0
    fitPercent.value = 100
  }

  function clampPan(px: number, py: number) {
    if (!imgRef.value || !containerRef.value) return { x: px, y: py }
    const cW = containerRef.value.clientWidth
    const cH = containerRef.value.clientHeight
    const scaledW = imgRef.value.clientWidth * zoomLevel.value
    const scaledH = imgRef.value.clientHeight * zoomLevel.value
    const maxX = Math.max(0, (scaledW - cW) / 2)
    const maxY = Math.max(0, (scaledH - cH) / 2)
    return {
      x: Math.max(-maxX, Math.min(maxX, px)),
      y: Math.max(-maxY, Math.min(maxY, py)),
    }
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault()
    const step = e.deltaY > 0 ? -0.1 : 0.1
    zoomLevel.value = Math.max(0.1, Math.min(10, +(zoomLevel.value + step).toFixed(1)))
    const c = clampPan(panX.value, panY.value)
    panX.value = c.x
    panY.value = c.y
  }

  function onImageLoad() {
    if (!imgRef.value) return
    const naturalW = imgRef.value.naturalWidth
    if (!naturalW) return
    fitPercent.value = Math.round((imgRef.value.clientWidth / naturalW) * 100)
  }

  function onMouseDown(e: MouseEvent) {
    if (e.button !== 0) return
    e.preventDefault()
    isDragging.value = true
    _dragStartX = e.clientX
    _dragStartY = e.clientY
    _panStartX = panX.value
    _panStartY = panY.value
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }

  function onMouseMove(e: MouseEvent) {
    if (!isDragging.value) return
    const c = clampPan(_panStartX + e.clientX - _dragStartX, _panStartY + e.clientY - _dragStartY)
    panX.value = c.x
    panY.value = c.y
  }

  function onMouseUp() {
    isDragging.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  onBeforeUnmount(() => {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  })

  const zoomPercent = computed(() => Math.round(fitPercent.value * zoomLevel.value))

  return {
    zoomLevel,
    panX,
    panY,
    isDragging,
    fitPercent,
    zoomPercent,
    reset,
    onWheel,
    onImageLoad,
    onMouseDown,
  }
}

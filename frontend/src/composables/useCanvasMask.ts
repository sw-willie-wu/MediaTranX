import { ref, watch, type Ref } from 'vue'

export type MaskToolMode = 'brush' | 'eraser' | 'polygon' | 'bezier'

export function useCanvasMask(
  imgRef: Ref<HTMLImageElement | null>,
  containerRef: Ref<HTMLElement | null>,
) {
  const canvasRef = ref<HTMLCanvasElement | null>(null)
  const brushSize = ref(10)
  const toolMode = ref<MaskToolMode>('brush')
  const isDrawing = ref(false)

  // ── Internal state ───────────────────────────────────────────
  let maskCanvas: HTMLCanvasElement | null = null
  let cursorX = -1
  let cursorY = -1

  // Brush: path tracking for auto-fill on closure
  let brushPath: { x: number; y: number }[] = []
  let isErasing = false  // Alt 按住時擦除模式

  // Polygon / Bezier: click-to-add vertices
  let vertices: { x: number; y: number }[] = []

  const MASK_COLOR = 'rgb(120, 80, 255)'

  watch(brushSize, () => redraw())
  watch(toolMode, () => {
    vertices = []
    brushPath = []
    isDrawing.value = false
    redraw()
  })

  // ── Helpers ────────────────────────────────────────────────

  function getMaskCanvas(w: number, h: number): HTMLCanvasElement {
    if (!maskCanvas || maskCanvas.width !== w || maskCanvas.height !== h) {
      maskCanvas = document.createElement('canvas')
      maskCanvas.width = w
      maskCanvas.height = h
    }
    return maskCanvas
  }

  function getScale(): number {
    const canvas = canvasRef.value
    if (!canvas) return 1
    const rect = canvas.getBoundingClientRect()
    return canvas.width / rect.width
  }

  function getCoords(e: MouseEvent) {
    const canvas = canvasRef.value!
    const rect = canvas.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) * (canvas.width / rect.width),
      y: (e.clientY - rect.top) * (canvas.height / rect.height),
    }
  }

  // ── Drawing primitives ─────────────────────────────────────

  function paintAt(x: number, y: number) {
    const canvas = canvasRef.value
    if (!canvas) return
    const scaledBrush = brushSize.value * getScale()
    const mc = getMaskCanvas(canvas.width, canvas.height)
    const mctx = mc.getContext('2d')!
    if (isErasing) {
      mctx.save()
      mctx.globalCompositeOperation = 'destination-out'
      mctx.beginPath()
      mctx.arc(x, y, scaledBrush, 0, Math.PI * 2)
      mctx.fill()
      mctx.restore()
    } else {
      mctx.beginPath()
      mctx.arc(x, y, scaledBrush, 0, Math.PI * 2)
      mctx.fillStyle = MASK_COLOR
      mctx.fill()
    }
    redraw()
  }

  function fillPolygon(points: { x: number; y: number }[]) {
    const canvas = canvasRef.value
    if (!canvas || points.length < 3) return
    const mc = getMaskCanvas(canvas.width, canvas.height)
    const ctx = mc.getContext('2d')!
    ctx.beginPath()
    ctx.moveTo(points[0].x, points[0].y)
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y)
    }
    ctx.closePath()
    ctx.fillStyle = MASK_COLOR
    ctx.fill()
    redraw()
  }

  function fillBezierShape(points: { x: number; y: number }[]) {
    const canvas = canvasRef.value
    if (!canvas || points.length < 3) return
    const mc = getMaskCanvas(canvas.width, canvas.height)
    const ctx = mc.getContext('2d')!
    ctx.beginPath()
    ctx.moveTo(points[0].x, points[0].y)

    // Closed Catmull-Rom → Bezier
    const n = points.length
    for (let i = 0; i < n; i++) {
      const p0 = points[(i - 1 + n) % n]
      const p1 = points[i]
      const p2 = points[(i + 1) % n]
      const p3 = points[(i + 2) % n]
      const cp1x = p1.x + (p2.x - p0.x) / 6
      const cp1y = p1.y + (p2.y - p0.y) / 6
      const cp2x = p2.x - (p3.x - p1.x) / 6
      const cp2y = p2.y - (p3.y - p1.y) / 6
      ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
    }

    ctx.closePath()
    ctx.fillStyle = MASK_COLOR
    ctx.fill()
    redraw()
  }

  // ── Redraw ─────────────────────────────────────────────────

  function redraw() {
    const canvas = canvasRef.value
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Mask layer (50% transparent)
    if (maskCanvas) {
      ctx.globalAlpha = 0.5
      ctx.drawImage(maskCanvas, 0, 0)
      ctx.globalAlpha = 1.0
    }

    const scale = getScale()
    if (toolMode.value === 'brush' || toolMode.value === 'eraser') {
      drawBrushCursor(ctx, scale)
    } else {
      drawShapePreview(ctx, scale)
      drawCrosshairCursor(ctx, scale)
    }
  }

  function drawBrushCursor(ctx: CanvasRenderingContext2D, scale: number) {
    if (cursorX < 0 || cursorY < 0) return
    const r = brushSize.value * scale
    // Black outline (thicker, behind)
    ctx.beginPath()
    ctx.arc(cursorX, cursorY, r, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)'
    ctx.lineWidth = 4
    ctx.stroke()
    // Ring color: red when erasing, white when painting
    ctx.beginPath()
    ctx.arc(cursorX, cursorY, r, 0, Math.PI * 2)
    ctx.strokeStyle = isErasing ? 'rgba(255, 100, 100, 0.9)' : 'rgba(255, 255, 255, 0.9)'
    ctx.lineWidth = 2
    ctx.stroke()
  }

  function drawCrosshairCursor(ctx: CanvasRenderingContext2D, scale: number) {
    if (cursorX < 0 || cursorY < 0) return
    const size = 12 * scale
    ctx.save()
    // Black outline
    ctx.lineWidth = 3
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.4)'
    ctx.beginPath()
    ctx.moveTo(cursorX - size, cursorY); ctx.lineTo(cursorX + size, cursorY)
    ctx.moveTo(cursorX, cursorY - size); ctx.lineTo(cursorX, cursorY + size)
    ctx.stroke()
    // White core
    ctx.lineWidth = 1.5
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)'
    ctx.beginPath()
    ctx.moveTo(cursorX - size, cursorY); ctx.lineTo(cursorX + size, cursorY)
    ctx.moveTo(cursorX, cursorY - size); ctx.lineTo(cursorX, cursorY + size)
    ctx.stroke()
    ctx.restore()
  }

  function drawShapePreview(ctx: CanvasRenderingContext2D, scale: number) {
    if (vertices.length === 0) return

    const closeThreshold = 15 * scale
    const isNearStart = cursorX >= 0 && cursorY >= 0 && vertices.length >= 3
      && Math.hypot(cursorX - vertices[0].x, cursorY - vertices[0].y) < closeThreshold

    ctx.save()
    ctx.lineWidth = 2 * scale
    ctx.setLineDash([6 * scale, 4 * scale])
    ctx.strokeStyle = 'rgba(168, 156, 200, 0.9)'

    if (toolMode.value === 'polygon') {
      ctx.beginPath()
      ctx.moveTo(vertices[0].x, vertices[0].y)
      for (let i = 1; i < vertices.length; i++) {
        ctx.lineTo(vertices[i].x, vertices[i].y)
      }
      // Preview line to cursor (or back to start if near)
      if (cursorX >= 0 && cursorY >= 0) {
        ctx.lineTo(isNearStart ? vertices[0].x : cursorX, isNearStart ? vertices[0].y : cursorY)
      }
      ctx.stroke()
    } else {
      // Bezier preview
      const pts = [...vertices]
      if (cursorX >= 0 && cursorY >= 0 && !isNearStart) {
        pts.push({ x: cursorX, y: cursorY })
      }
      drawBezierPath(ctx, pts, isNearStart)
    }

    ctx.restore()
    drawVertexMarkers(ctx, scale, isNearStart)
  }

  function drawBezierPath(
    ctx: CanvasRenderingContext2D,
    pts: { x: number; y: number }[],
    closed: boolean,
  ) {
    if (pts.length < 2) return
    ctx.beginPath()
    ctx.moveTo(pts[0].x, pts[0].y)

    if (pts.length === 2) {
      ctx.lineTo(pts[1].x, pts[1].y)
    } else if (closed) {
      // Closed Catmull-Rom
      const n = pts.length
      for (let i = 0; i < n; i++) {
        const p0 = pts[(i - 1 + n) % n]
        const p1 = pts[i]
        const p2 = pts[(i + 1) % n]
        const p3 = pts[(i + 2) % n]
        const cp1x = p1.x + (p2.x - p0.x) / 6
        const cp1y = p1.y + (p2.y - p0.y) / 6
        const cp2x = p2.x - (p3.x - p1.x) / 6
        const cp2y = p2.y - (p3.y - p1.y) / 6
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
      }
    } else {
      // Open Catmull-Rom (clamped ends)
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[Math.max(0, i - 1)]
        const p1 = pts[i]
        const p2 = pts[i + 1]
        const p3 = pts[Math.min(pts.length - 1, i + 2)]
        const cp1x = p1.x + (p2.x - p0.x) / 6
        const cp1y = p1.y + (p2.y - p0.y) / 6
        const cp2x = p2.x - (p3.x - p1.x) / 6
        const cp2y = p2.y - (p3.y - p1.y) / 6
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y)
      }
    }
    ctx.stroke()
  }

  function drawVertexMarkers(
    ctx: CanvasRenderingContext2D,
    scale: number,
    isNearStart: boolean,
  ) {
    const r = 4 * scale
    for (let i = 0; i < vertices.length; i++) {
      const v = vertices[i]
      // Fill
      ctx.beginPath()
      ctx.arc(v.x, v.y, r, 0, Math.PI * 2)
      ctx.fillStyle = i === 0 ? 'rgba(168, 156, 200, 0.9)' : 'rgba(255, 255, 255, 0.8)'
      ctx.fill()
      // Stroke
      ctx.beginPath()
      ctx.arc(v.x, v.y, r, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)'
      ctx.lineWidth = 1.5 * scale
      ctx.setLineDash([])
      ctx.stroke()

      // Close hint ring on start vertex
      if (i === 0 && isNearStart) {
        ctx.beginPath()
        ctx.arc(v.x, v.y, r * 2.5, 0, Math.PI * 2)
        ctx.strokeStyle = 'rgba(168, 156, 200, 0.6)'
        ctx.lineWidth = 2 * scale
        ctx.stroke()
      }
    }
  }

  // ── Event handlers ─────────────────────────────────────────

  function onMouseDown(e: MouseEvent) {
    // 只處理左鍵（右鍵由 onContextMenu 處理）
    if (e.button !== 0) return
    const { x, y } = getCoords(e)

    if (toolMode.value === 'brush' || toolMode.value === 'eraser') {
      isErasing = toolMode.value === 'eraser' || e.altKey
      isDrawing.value = true
      brushPath = isErasing ? [] : [{ x, y }]
      paintAt(x, y)
    } else {
      // Polygon / Bezier: add vertex (or close if near start)
      const closeThreshold = 15 * getScale()
      if (vertices.length >= 3) {
        const dist = Math.hypot(x - vertices[0].x, y - vertices[0].y)
        if (dist < closeThreshold) {
          closeShape()
          return
        }
      }
      vertices.push({ x, y })
      redraw()
    }
  }

  function onMouseMove(e: MouseEvent) {
    const { x, y } = getCoords(e)
    cursorX = x
    cursorY = y
    if (toolMode.value === 'brush' || toolMode.value === 'eraser') {
      // 即時追蹤 Alt 狀態（游標顏色隨按鍵變化）
      if (!isDrawing.value) isErasing = toolMode.value === 'eraser' || e.altKey
      if (isDrawing.value) {
        if (!isErasing) brushPath.push({ x, y })
        paintAt(x, y)
      } else {
        redraw()
      }
    } else {
      redraw()
    }
  }

  function onMouseUp() {
    if (toolMode.value === 'brush' || toolMode.value === 'eraser') {
      isDrawing.value = false
      // 擦除模式不做閉合填充
      if (isErasing) { brushPath = []; isErasing = false; return }
      // Auto-fill on closure: if brush path loops back near start
      if (brushPath.length > 20) {
        const start = brushPath[0]
        const end = brushPath[brushPath.length - 1]
        const scale = getScale()
        const threshold = Math.max(brushSize.value * scale * 2, 20 * scale)
        const dist = Math.hypot(end.x - start.x, end.y - start.y)
        if (dist < threshold) {
          fillPolygon(brushPath)
        }
      }
      brushPath = []
    }
  }

  function onMouseLeave() {
    if (toolMode.value === 'brush' || toolMode.value === 'eraser') {
      isDrawing.value = false
      brushPath = []
    }
    cursorX = -1
    cursorY = -1
    redraw()
  }

  function onDblClick() {
    if (toolMode.value !== 'brush' && vertices.length >= 3) {
      closeShape()
    }
  }

  /** 右鍵：撤回上一個頂點 */
  function onContextMenu(e: MouseEvent) {
    e.preventDefault()
    if (toolMode.value !== 'brush' && vertices.length > 0) {
      vertices.pop()
      redraw()
    }
  }

  function closeShape() {
    if (vertices.length < 3) { vertices = []; redraw(); return }
    if (toolMode.value === 'polygon') fillPolygon(vertices)
    else if (toolMode.value === 'bezier') fillBezierShape(vertices)
    vertices = []
    redraw()
  }

  function cancelShape() {
    vertices = []
    redraw()
  }

  // ── Sync / Export / Clear ──────────────────────────────────

  /** 同步 canvas 位置與尺寸到圖片元素（排除 object-fit: contain 的 letterbox 區域） */
  function syncToImage() {
    const img = imgRef.value
    const container = containerRef.value
    const canvas = canvasRef.value
    if (!img || !container || !canvas || !img.naturalWidth) return

    const imgRect = img.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()

    const nw = img.naturalWidth
    const nh = img.naturalHeight
    const scale = Math.min(imgRect.width / nw, imgRect.height / nh)
    const contentW = nw * scale
    const contentH = nh * scale
    const contentLeft = imgRect.left + (imgRect.width - contentW) / 2
    const contentTop = imgRect.top + (imgRect.height - contentH) / 2

    canvas.style.left = `${contentLeft - containerRect.left}px`
    canvas.style.top = `${contentTop - containerRect.top}px`
    canvas.style.width = `${contentW}px`
    canvas.style.height = `${contentH}px`
    canvas.width = nw
    canvas.height = nh
    getMaskCanvas(canvas.width, canvas.height)
    redraw()
  }

  function clearMask() {
    const canvas = canvasRef.value
    if (!canvas) return
    if (maskCanvas) {
      maskCanvas.getContext('2d')!.clearRect(0, 0, maskCanvas.width, maskCanvas.height)
    }
    canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
    vertices = []
    brushPath = []
  }

  function hasMask(): boolean {
    if (!maskCanvas) return false
    const data = maskCanvas.getContext('2d')!.getImageData(0, 0, maskCanvas.width, maskCanvas.height).data
    for (let i = 3; i < data.length; i += 4) {
      if (data[i] > 10) return true
    }
    return false
  }

  /** 匯出遮罩：白色=要移除區域，黑色=保留 */
  function exportMask(): string | null {
    const canvas = canvasRef.value
    if (!canvas) return null
    const mc = maskCanvas ?? canvas

    const offscreen = document.createElement('canvas')
    offscreen.width = mc.width
    offscreen.height = mc.height
    const ctx = offscreen.getContext('2d')!

    ctx.fillStyle = 'black'
    ctx.fillRect(0, 0, offscreen.width, offscreen.height)

    const srcData = mc.getContext('2d')!.getImageData(0, 0, mc.width, mc.height)
    const dstData = ctx.createImageData(mc.width, mc.height)
    for (let i = 0; i < srcData.data.length; i += 4) {
      const v = srcData.data[i + 3] > 10 ? 255 : 0
      dstData.data[i]     = v
      dstData.data[i + 1] = v
      dstData.data[i + 2] = v
      dstData.data[i + 3] = 255
    }
    ctx.putImageData(dstData, 0, 0)
    return offscreen.toDataURL('image/png')
  }

  return {
    canvasRef,
    brushSize,
    toolMode,
    isDrawing,
    syncToImage,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onMouseLeave,
    onDblClick,
    onContextMenu,
    cancelShape,
    clearMask,
    hasMask,
    exportMask,
  }
}

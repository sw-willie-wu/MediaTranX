import { ref, type Ref } from 'vue'

export function useCanvasMask(
  imgRef: Ref<HTMLImageElement | null>,
  containerRef: Ref<HTMLElement | null>,
) {
  const canvasRef = ref<HTMLCanvasElement | null>(null)
  const brushSize = ref(10)
  const isDrawing = ref(false)

  // offscreen canvas 儲存二值遮罩（白=塗抹），顯示用 canvas 以固定透明度呈現
  let maskCanvas: HTMLCanvasElement | null = null
  let cursorX = -1
  let cursorY = -1

  function getMaskCanvas(w: number, h: number): HTMLCanvasElement {
    if (!maskCanvas || maskCanvas.width !== w || maskCanvas.height !== h) {
      maskCanvas = document.createElement('canvas')
      maskCanvas.width = w
      maskCanvas.height = h
    }
    return maskCanvas
  }

  function redraw() {
    const canvas = canvasRef.value
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 畫遮罩層（50% 透明）
    if (maskCanvas) {
      ctx.globalAlpha = 0.5
      ctx.drawImage(maskCanvas, 0, 0)
      ctx.globalAlpha = 1.0
    }

    // 畫空心圓形游標
    if (cursorX >= 0 && cursorY >= 0) {
      const rect = canvas.getBoundingClientRect()
      const r = brushSize.value * (canvas.width / rect.width)
      ctx.beginPath()
      ctx.arc(cursorX, cursorY, r, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)'
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(cursorX, cursorY, r, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)'
      ctx.lineWidth = 4
      ctx.stroke()
    }
  }

  /** 同步 canvas 位置與尺寸到圖片元素 */
  function syncToImage() {
    const img = imgRef.value
    const container = containerRef.value
    const canvas = canvasRef.value
    if (!img || !container || !canvas || !img.naturalWidth) return

    const imgRect = img.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()

    canvas.style.left = `${imgRect.left - containerRect.left}px`
    canvas.style.top = `${imgRect.top - containerRect.top}px`
    canvas.style.width = `${imgRect.width}px`
    canvas.style.height = `${imgRect.height}px`
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    // 同步 offscreen 遮罩尺寸（保留已畫內容）
    getMaskCanvas(canvas.width, canvas.height)
    redraw()
  }

  function getCoords(e: MouseEvent) {
    const canvas = canvasRef.value!
    const rect = canvas.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) * (canvas.width / rect.width),
      y: (e.clientY - rect.top) * (canvas.height / rect.height),
    }
  }

  function paintAt(x: number, y: number) {
    const canvas = canvasRef.value
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const scaledBrush = brushSize.value * (canvas.width / rect.width)

    // 畫到 offscreen 遮罩（純色，不透明）
    const mc = getMaskCanvas(canvas.width, canvas.height)
    const mctx = mc.getContext('2d')!
    mctx.beginPath()
    mctx.arc(x, y, scaledBrush, 0, Math.PI * 2)
    mctx.fillStyle = 'rgb(120, 80, 255)'
    mctx.fill()

    // 以固定 50% 透明度重繪顯示層
    redraw()
  }

  function onMouseDown(e: MouseEvent) {
    isDrawing.value = true
    const { x, y } = getCoords(e)
    paintAt(x, y)
  }

  function onMouseMove(e: MouseEvent) {
    const { x, y } = getCoords(e)
    cursorX = x
    cursorY = y
    if (isDrawing.value) paintAt(x, y)
    else redraw()
  }

  function onMouseUp() {
    isDrawing.value = false
  }

  function onMouseLeave() {
    isDrawing.value = false
    cursorX = -1
    cursorY = -1
    redraw()
  }

  function clearMask() {
    const canvas = canvasRef.value
    if (!canvas) return
    if (maskCanvas) {
      maskCanvas.getContext('2d')!.clearRect(0, 0, maskCanvas.width, maskCanvas.height)
    }
    canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
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
    isDrawing,
    syncToImage,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onMouseLeave,
    clearMask,
    hasMask,
    exportMask,
  }
}

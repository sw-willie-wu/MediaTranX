import { ref, watch, type Ref } from 'vue'

export interface CropRect { x: number; y: number; w: number; h: number }

type Handle = 'TL' | 'T' | 'TR' | 'R' | 'BR' | 'B' | 'BL' | 'L' | 'move'

const HANDLE_CURSORS: Record<Handle, string> = {
  TL: 'nwse-resize', T: 'ns-resize',   TR: 'nesw-resize',
  R:  'ew-resize',   BR: 'nwse-resize', B: 'ns-resize',
  BL: 'nesw-resize', L: 'ew-resize',   move: 'move',
}

export function useCropRect(
  imgRef: Ref<HTMLImageElement | null>,
  containerRef: Ref<HTMLElement | null>,
  aspectRatioRef: Ref<string>,
) {
  const canvasRef = ref<HTMLCanvasElement | null>(null)
  const cropRect = ref<CropRect | null>(null)

  let dragHandle: Handle | null = null
  let dragStartX = 0
  let dragStartY = 0
  let dragStartRect: CropRect | null = null

  // ── 長寬比計算 ──────────────────────────────────────────────────────────

  function getRatio(): number | null {
    const ar = aspectRatioRef.value
    if (ar === 'free') return null
    const [w, h] = ar.split(':').map(Number)
    return w && h ? w / h : null
  }

  // ── 座標轉換 ─────────────────────────────────────────────────────────────

  function getCoords(e: MouseEvent): { x: number; y: number } {
    const canvas = canvasRef.value!
    const rect = canvas.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) * (canvas.width  / rect.width),
      y: (e.clientY - rect.top)  * (canvas.height / rect.height),
    }
  }

  function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)) }

  // ── 把手位置 ─────────────────────────────────────────────────────────────

  function handles(r: CropRect): Record<Handle, [number, number]> {
    return {
      TL: [r.x,           r.y          ],
      T:  [r.x + r.w / 2, r.y          ],
      TR: [r.x + r.w,     r.y          ],
      R:  [r.x + r.w,     r.y + r.h / 2],
      BR: [r.x + r.w,     r.y + r.h    ],
      B:  [r.x + r.w / 2, r.y + r.h    ],
      BL: [r.x,           r.y + r.h    ],
      L:  [r.x,           r.y + r.h / 2],
      move: [r.x + r.w / 2, r.y + r.h / 2],
    }
  }

  function hitRadius(): number {
    const canvas = canvasRef.value
    if (!canvas) return 12
    const rect = canvas.getBoundingClientRect()
    return Math.max(10, 14 * (canvas.width / rect.width))
  }

  function hitTest(mx: number, my: number): Handle | null {
    const r = cropRect.value
    if (!r) return null
    const hr = hitRadius()
    const hmap = handles(r)
    for (const key of ['TL','T','TR','R','BR','B','BL','L'] as Handle[]) {
      const [hx, hy] = hmap[key]
      if (Math.abs(mx - hx) <= hr && Math.abs(my - hy) <= hr) return key
    }
    // 內部（排除把手邊緣）
    const pad = hr
    if (mx > r.x + pad && mx < r.x + r.w - pad &&
        my > r.y + pad && my < r.y + r.h - pad) return 'move'
    return null
  }

  // ── Resize 邏輯（長寬比約束）────────────────────────────────────────────

  function applyResize(handle: Handle, dx: number, dy: number): CropRect {
    const s = dragStartRect!
    const ratio = getRatio()
    const canvas = canvasRef.value
    const W = canvas?.width  ?? 99999
    const H = canvas?.height ?? 99999
    const MIN = 20

    let { x, y, w, h } = s

    if (handle === 'move') {
      x = clamp(s.x + dx, 0, W - w)
      y = clamp(s.y + dy, 0, H - h)
      return { x, y, w, h }
    }

    // 根據把手計算新的矩形（不帶比例約束）
    let nx = s.x, ny = s.y, nw = s.w, nh = s.h

    if (handle === 'TL') { nx = s.x + dx; ny = s.y + dy; nw = s.w - dx; nh = s.h - dy }
    if (handle === 'T')  {               ny = s.y + dy;             nh = s.h - dy }
    if (handle === 'TR') {               ny = s.y + dy; nw = s.w + dx; nh = s.h - dy }
    if (handle === 'R')  {                              nw = s.w + dx }
    if (handle === 'BR') {                              nw = s.w + dx; nh = s.h + dy }
    if (handle === 'B')  {                                             nh = s.h + dy }
    if (handle === 'BL') { nx = s.x + dx;              nw = s.w - dx; nh = s.h + dy }
    if (handle === 'L')  { nx = s.x + dx;              nw = s.w - dx }

    // 套用長寬比
    if (ratio) {
      if (['T', 'B'].includes(handle)) {
        // 垂直邊：以高度為基準計算寬，以原中心對齊
        const newW = nh * ratio
        nx = s.x + (s.w - newW) / 2
        nw = newW
      } else if (['L', 'R'].includes(handle)) {
        // 水平邊：以寬度為基準計算高，以原中心對齊
        const newH = nw / ratio
        ny = s.y + (s.h - newH) / 2
        nh = newH
      } else {
        // 角落：以較大軸為基準
        const bByW = nw / ratio
        const bByH = nh * ratio
        if (Math.abs(dx) >= Math.abs(dy)) {
          // 寬度主導
          nh = bByW
          if (handle === 'TL') ny = s.y + s.h - nh
          if (handle === 'TR') ny = s.y + s.h - nh
        } else {
          // 高度主導
          nw = bByH
          if (handle === 'TL') nx = s.x + s.w - nw
          if (handle === 'BL') nx = s.x + s.w - nw
        }
      }
    }

    // 最小尺寸
    if (nw < MIN) { if (['TL','L','BL'].includes(handle)) nx = s.x + s.w - MIN; nw = MIN }
    if (nh < MIN) { if (['TL','T','TR'].includes(handle)) ny = s.y + s.h - MIN; nh = MIN }

    // 邊界 clamp
    nx = clamp(nx, 0, W - MIN)
    ny = clamp(ny, 0, H - MIN)
    nw = clamp(nw, MIN, W - nx)
    nh = clamp(nh, MIN, H - ny)

    return { x: Math.round(nx), y: Math.round(ny), w: Math.round(nw), h: Math.round(nh) }
  }

  // ── 繪製 ─────────────────────────────────────────────────────────────────

  function redraw() {
    const canvas = canvasRef.value
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    const r = cropRect.value
    if (!r) return

    // 暗化外部
    ctx.fillStyle = 'rgba(0, 0, 0, 0.65)'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.clearRect(r.x, r.y, r.w, r.h)

    // 邊框（外層黑色陰影 + 內層亮色）
    // 內縮半個線寬，避免在 canvas 邊緣被裁切
    const lw = Math.max(3, canvas.width / 150)
    const half = (lw + 2) / 2
    const bx = r.x + half, by = r.y + half, bw = r.w - half * 2, bh = r.h - half * 2
    ctx.save()
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.lineWidth = lw + 2
    ctx.setLineDash([])
    ctx.strokeRect(bx, by, bw, bh)
    ctx.restore()

    const half2 = lw / 2
    const cx = r.x + half2, cy = r.y + half2, cw = r.w - half2 * 2, ch = r.h - half2 * 2
    ctx.save()
    ctx.strokeStyle = 'rgba(96, 165, 250, 1)'
    ctx.lineWidth = lw
    ctx.setLineDash([])
    ctx.strokeRect(cx, cy, cw, ch)
    ctx.restore()

    // 三分線
    ctx.save()
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)'
    ctx.lineWidth = Math.max(1, canvas.width / 1000)
    ctx.beginPath()
    for (let i = 1; i < 3; i++) {
      ctx.moveTo(r.x + r.w * i / 3, r.y); ctx.lineTo(r.x + r.w * i / 3, r.y + r.h)
      ctx.moveTo(r.x, r.y + r.h * i / 3); ctx.lineTo(r.x + r.w, r.y + r.h * i / 3)
    }
    ctx.stroke()
    ctx.restore()

    // 8 個把手（藍色填充 + 白色邊框，內縮避免邊緣裁切）
    const hmap = handles(r)
    const hs = Math.max(10, canvas.width / 60)
    const hlw = Math.max(1.5, canvas.width / 600)
    const W = canvas.width, H = canvas.height
    for (const key of ['TL','T','TR','R','BR','B','BL','L'] as Handle[]) {
      const [hx, hy] = hmap[key]
      const hxi = clamp(hx - hs / 2, hlw / 2, W - hs - hlw / 2)
      const hyi = clamp(hy - hs / 2, hlw / 2, H - hs - hlw / 2)
      ctx.fillStyle = 'rgba(96, 165, 250, 1)'
      ctx.strokeStyle = 'white'
      ctx.lineWidth = hlw
      ctx.fillRect(hxi, hyi, hs, hs)
      ctx.strokeRect(hxi + hlw / 2, hyi + hlw / 2, hs - hlw, hs - hlw)
    }
  }

  // ── syncToImage & 初始化 ────────────────────────────────────────────────

  function initDefaultRect() {
    const canvas = canvasRef.value
    if (!canvas || !canvas.width) return
    const W = canvas.width, H = canvas.height
    const ratio = getRatio()
    if (!ratio) {
      cropRect.value = { x: 0, y: 0, w: W, h: H }
    } else {
      const hFromW = W / ratio
      if (hFromW <= H) {
        cropRect.value = { x: 0, y: Math.round((H - hFromW) / 2), w: W, h: Math.round(hFromW) }
      } else {
        const wFromH = H * ratio
        cropRect.value = { x: Math.round((W - wFromH) / 2), y: 0, w: Math.round(wFromH), h: H }
      }
    }
  }

  // 只更新 canvas 的 CSS 位置/尺寸，不重置裁切矩形（用於縮放/拖曳時）
  function repositionCanvas() {
    const img = imgRef.value
    const container = containerRef.value
    const canvas = canvasRef.value
    if (!img || !container || !canvas) return

    const imgRect = img.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()

    canvas.style.left   = `${imgRect.left - containerRect.left}px`
    canvas.style.top    = `${imgRect.top  - containerRect.top}px`
    canvas.style.width  = `${imgRect.width}px`
    canvas.style.height = `${imgRect.height}px`
  }

  function syncToImage() {
    const img = imgRef.value
    const container = containerRef.value
    const canvas = canvasRef.value
    if (!img || !container || !canvas || !img.naturalWidth) return

    repositionCanvas()
    canvas.width  = img.naturalWidth
    canvas.height = img.naturalHeight

    initDefaultRect()
    redraw()
  }

  // 長寬比改變時重新初始化
  watch(aspectRatioRef, () => {
    if (!cropRect.value) return
    initDefaultRect()
    redraw()
  })

  // ── 滑鼠事件 ─────────────────────────────────────────────────────────────

  function onMouseDown(e: MouseEvent) {
    const { x, y } = getCoords(e)
    const hit = hitTest(x, y)
    if (!hit) return
    dragHandle = hit
    dragStartX = x
    dragStartY = y
    dragStartRect = cropRect.value ? { ...cropRect.value } : null
  }

  function onMouseMove(e: MouseEvent) {
    const canvas = canvasRef.value
    if (!canvas) return
    const { x, y } = getCoords(e)

    if (dragHandle && dragStartRect) {
      cropRect.value = applyResize(dragHandle, x - dragStartX, y - dragStartY)
      redraw()
      return
    }

    const hit = hitTest(x, y)
    canvas.style.cursor = hit ? HANDLE_CURSORS[hit] : 'default'
  }

  function onMouseUp() {
    dragHandle = null
    dragStartRect = null
  }

  function onMouseLeave() {
    dragHandle = null
    dragStartRect = null
    const canvas = canvasRef.value
    if (canvas) canvas.style.cursor = 'default'
  }

  function clearRect() {
    dragHandle = null
    dragStartRect = null
    cropRect.value = null
    const canvas = canvasRef.value
    if (canvas) canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
  }

  return {
    canvasRef, cropRect,
    syncToImage, repositionCanvas, initDefaultRect, redraw,
    onMouseDown, onMouseMove, onMouseUp, onMouseLeave,
    clearRect,
  }
}

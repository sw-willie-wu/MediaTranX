import { ref, watch, type Ref } from 'vue'

export interface CropRect { x: number; y: number; w: number; h: number }

type Handle = 'TL' | 'T' | 'TR' | 'R' | 'BR' | 'B' | 'BL' | 'L' | 'move'

const HANDLE_CURSORS: Record<Handle, string> = {
  TL: 'nwse-resize', T: 'ns-resize',   TR: 'nesw-resize',
  R:  'ew-resize',   BR: 'nwse-resize', B: 'ns-resize',
  BL: 'nesw-resize', L: 'ew-resize',   move: 'move',
}

// Canvas padding 設為 0 — canvas 完全對齊圖片，邊緣把手會被裁切但功能不影響
const CANVAS_PAD = 0

type MediaEl = HTMLImageElement | HTMLVideoElement

function intrinsicSize(el: MediaEl): { w: number; h: number } {
  if (el instanceof HTMLVideoElement) return { w: el.videoWidth, h: el.videoHeight }
  return { w: el.naturalWidth, h: el.naturalHeight }
}

function intrinsicSrc(el: MediaEl): string {
  return el.src || ''
}

export function useCropRect(
  mediaRef: Ref<MediaEl | null>,
  containerRef: Ref<HTMLElement | null>,
  aspectRatioRef: Ref<string>,
) {
  const canvasRef = ref<HTMLCanvasElement | null>(null)
  const cropRect = ref<CropRect | null>(null)
  let _lastImgSrc = ''
  const _rectCache = new Map<string, CropRect>()  // per-image 裁切框快取

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

  // ── 影像尺寸（去掉 padding 後的實際寬高）────────────────────────────────

  function imgDims(): { W: number; H: number } {
    const canvas = canvasRef.value
    if (!canvas) return { W: 99999, H: 99999 }
    return { W: canvas.width - 2 * CANVAS_PAD, H: canvas.height - 2 * CANVAS_PAD }
  }

  // ── 座標轉換 ─────────────────────────────────────────────────────────────
  // getCoords 回傳「影像空間」座標（已去除 padding offset）

  function getCoords(e: MouseEvent): { x: number; y: number } {
    const canvas = canvasRef.value!
    const rect = canvas.getBoundingClientRect()
    return {
      x: (e.clientX - rect.left) * (canvas.width  / rect.width)  - CANVAS_PAD,
      y: (e.clientY - rect.top)  * (canvas.height / rect.height) - CANVAS_PAD,
    }
  }

  function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)) }

  // ── 把手位置（影像空間）──────────────────────────────────────────────────

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
    // canvas.width includes 2*CANVAS_PAD; display scale is rect.width / canvas.width
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
    const { W, H } = imgDims()
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
  // 所有座標在 canvas 空間（需加上 CANVAS_PAD offset）

  function redraw() {
    const canvas = canvasRef.value
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    const r = cropRect.value
    if (!r) return

    // 將影像空間座標轉為 canvas 空間（加 padding）
    const P = CANVAS_PAD
    const rx = r.x + P, ry = r.y + P

    // 暗化外部（只暗影像區域，padding 保持透明）
    const { W, H } = imgDims()
    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
    ctx.fillRect(P, P, W, H)
    ctx.clearRect(rx, ry, r.w, r.h)

    // 邊框（外層黑色陰影 + 內層亮色）
    const lw = Math.max(1.5, W / 300)
    const half = (lw + 2) / 2
    ctx.save()
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.lineWidth = lw + 2
    ctx.setLineDash([])
    ctx.strokeRect(rx + half, ry + half, r.w - half * 2, r.h - half * 2)
    ctx.restore()

    const half2 = lw / 2
    ctx.save()
    ctx.strokeStyle = 'rgba(96, 165, 250, 1)'
    ctx.lineWidth = lw
    ctx.setLineDash([])
    ctx.strokeRect(rx + half2, ry + half2, r.w - half2 * 2, r.h - half2 * 2)
    ctx.restore()

    // 三分線
    ctx.save()
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)'
    ctx.lineWidth = Math.max(1, W / 1000)
    ctx.beginPath()
    for (let i = 1; i < 3; i++) {
      ctx.moveTo(rx + r.w * i / 3, ry);      ctx.lineTo(rx + r.w * i / 3, ry + r.h)
      ctx.moveTo(rx,               ry + r.h * i / 3); ctx.lineTo(rx + r.w, ry + r.h * i / 3)
    }
    ctx.stroke()
    ctx.restore()

    // 8 個把手（藍色填充 + 白色邊框）
    // 把手中心 = 邊線中心點（影像空間）+ padding → canvas 空間
    const hmap = handles(r)
    const hs = Math.max(5, W / 120)
    const hlw = Math.max(1, W / 800)
    for (const key of ['TL','T','TR','R','BR','B','BL','L'] as Handle[]) {
      const [hx, hy] = hmap[key]
      // canvas 空間 = 影像空間 + P，置中 = - hs/2
      const hxi = hx + P - hs / 2
      const hyi = hy + P - hs / 2
      ctx.fillStyle = 'rgba(96, 165, 250, 1)'
      ctx.strokeStyle = 'white'
      ctx.lineWidth = hlw
      ctx.fillRect(hxi, hyi, hs, hs)
      ctx.strokeRect(hxi + hlw / 2, hyi + hlw / 2, hs - hlw, hs - hlw)
    }
  }

  // ── syncToImage & 初始化 ────────────────────────────────────────────────

  function initDefaultRect() {
    const { W, H } = imgDims()
    if (!W || W === 99999) return
    const ratio = getRatio()

    // 預設裁切框：1/4 面積（50% 寬高），左上 10% offset
    let cw = Math.round(W * 0.5)
    let ch = Math.round(H * 0.5)
    let cx = Math.round(W * 0.1)
    let cy = Math.round(H * 0.1)

    if (ratio) {
      // 有固定比例時，以寬為基準計算高
      const hFromW = cw / ratio
      if (hFromW <= H * 0.8) {
        ch = Math.round(hFromW)
      } else {
        ch = Math.round(H * 0.5)
        cw = Math.round(ch * ratio)
      }
      // 置中
      cx = Math.round((W - cw) / 2)
      cy = Math.round((H - ch) / 2)
    }

    cropRect.value = { x: cx, y: cy, w: cw, h: ch }
  }

  // 只更新 canvas 的 CSS 位置/尺寸，不重置裁切矩形（用於縮放/拖曳時）
  // canvas 比影像大 CANVAS_PAD 圈，所以 CSS 要向外偏移
  function repositionCanvas() {
    const media = mediaRef.value
    const container = containerRef.value
    const canvas = canvasRef.value
    if (!media || !container || !canvas) return

    const imgRect = media.getBoundingClientRect()
    const containerRect = container.getBoundingClientRect()

    // object-fit: contain 後的實際圖片顯示尺寸（不是元素 box 尺寸）
    const { w: nw, h: nh } = intrinsicSize(media)
    const boxW = imgRect.width, boxH = imgRect.height
    const scale = Math.min(boxW / nw, boxH / nh)
    const displayW = nw * scale
    const displayH = nh * scale
    // 圖片在元素 box 內置中
    const offsetX = (boxW - displayW) / 2
    const offsetY = (boxH - displayH) / 2

    canvas.style.left   = `${imgRect.left - containerRect.left + offsetX}px`
    canvas.style.top    = `${imgRect.top  - containerRect.top  + offsetY}px`
    canvas.style.width  = `${displayW}px`
    canvas.style.height = `${displayH}px`
  }

  function syncToImage(forceReset = false) {
    const media = mediaRef.value
    const container = containerRef.value
    const canvas = canvasRef.value
    if (!media || !container || !canvas || !intrinsicSize(media).w) return

    // 偵測圖片切換 → 存舊的、還原或重設
    const currentSrc = intrinsicSrc(media)
    if (currentSrc !== _lastImgSrc) {
      // 存前一張的裁切框
      if (_lastImgSrc && cropRect.value) {
        _rectCache.set(_lastImgSrc, { ...cropRect.value })
      }
      _lastImgSrc = currentSrc

      // 嘗試還原快取
      const cached = _rectCache.get(currentSrc)
      if (cached) {
        cropRect.value = { ...cached }
      } else {
        cropRect.value = null  // 讓下面 initDefaultRect
      }
    }

    repositionCanvas()
    const { w: nw, h: nh } = intrinsicSize(media)
    canvas.width  = nw + 2 * CANVAS_PAD
    canvas.height = nh + 2 * CANVAS_PAD

    if (!cropRect.value || forceReset) {
      initDefaultRect()
    }
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

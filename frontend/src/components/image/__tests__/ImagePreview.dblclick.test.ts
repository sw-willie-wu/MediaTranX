/** @vitest-environment jsdom */
/**
 * ImagePreview 雙擊還原 fit（v1.7.1 B）+ AiRemove gate。
 * mock 重相依（canvas mask/crop/WebGL），保留 useImageZoom 真值以驗 reset。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

const stubRef = () => ref(null)
vi.mock('@/composables/useCanvasMask', () => ({
  useCanvasMask: () => ({
    canvasRef: stubRef(), brushSize: ref(10), toolMode: ref('brush'),
    syncToImage: vi.fn(), onMouseDown: vi.fn(), onMouseMove: vi.fn(), onMouseUp: vi.fn(),
    onMouseLeave: vi.fn(), onDblClick: vi.fn(), onContextMenu: vi.fn(), cancelShape: vi.fn(),
    clearMask: vi.fn(), hasMask: ref(false), exportMask: vi.fn(),
  }),
}))
vi.mock('@/composables/useCropRect', () => ({
  useCropRect: () => ({
    canvasRef: stubRef(), cropRect: ref(null), syncToImage: vi.fn(), repositionCanvas: vi.fn(),
    onMouseDown: vi.fn(), onMouseMove: vi.fn(), onMouseUp: vi.fn(), onMouseLeave: vi.fn(), clearRect: vi.fn(),
  }),
}))
vi.mock('@/composables/useWebGLFilter', () => ({
  useWebGLFilter: () => ({
    isReady: ref(false), isSupported: ref(false), loadImage: vi.fn(), updateFilters: vi.fn(), dispose: vi.fn(),
  }),
}))

import ImagePreview from '@/components/image/ImagePreview.vue'

function mountPreview(isAiRemoveMode = false) {
  return mount(ImagePreview, {
    props: {
      previewUrl: 'blob:x', imageInfo: null, isAiRemoveMode,
      showCropOverlay: false,
    },
  })
}

describe('ImagePreview — 雙擊還原 fit', () => {
  it('一般模式雙擊 → reset（zoomLevel 回 1、pan 歸零）', async () => {
    const w = mountPreview(false)
    ;(w.vm as any).setZoom(3)
    expect((w.vm as any).zoomLevel).toBe(3)
    await w.find('.preview-image').trigger('dblclick')
    expect((w.vm as any).zoomLevel).toBe(1)
  })

  it('AiRemove 模式雙擊 → 不 reset（讓給 mask-canvas 封閉形狀）', async () => {
    const w = mountPreview(true)
    ;(w.vm as any).setZoom(3)
    await w.find('.preview-image').trigger('dblclick')
    expect((w.vm as any).zoomLevel).toBe(3) // 維持不變
  })
})

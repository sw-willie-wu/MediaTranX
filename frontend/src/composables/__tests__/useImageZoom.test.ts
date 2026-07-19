/** @vitest-environment jsdom */
import { describe, it, expect } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { useImageZoom, ZOOM_MIN, ZOOM_MAX } from '@/composables/useImageZoom'

// useImageZoom 內呼叫 onBeforeUnmount → 需 setup context；用最小元件包裝取回 handle。
function make() {
  let z!: ReturnType<typeof useImageZoom>
  mount(defineComponent({
    setup() {
      const img = ref<HTMLImageElement | null>(null)
      const container = ref<HTMLElement | null>(null)
      z = useImageZoom(img as never, container as never)
      return () => null
    },
  }))
  return z
}

describe('useImageZoom.setZoom', () => {
  it('clamps to [ZOOM_MIN, ZOOM_MAX]', () => {
    const z = make()
    z.setZoom(0.01); expect(z.zoomLevel.value).toBe(ZOOM_MIN)
    z.setZoom(99);   expect(z.zoomLevel.value).toBe(ZOOM_MAX)
    z.setZoom(2.5);  expect(z.zoomLevel.value).toBe(2.5)
  })
})

describe('useImageZoom.reset', () => {
  it('回 fit：zoomLevel=1、pan 歸零、fitPercent 不動', () => {
    const z = make()
    z.fitPercent.value = 37
    z.setZoom(3)
    z.panX.value = 50
    z.reset()
    expect(z.zoomLevel.value).toBe(1)
    expect(z.panX.value).toBe(0)
    expect(z.panY.value).toBe(0)
    expect(z.fitPercent.value).toBe(37) // 不動——2026-07-13 修過的不變量
  })

  it('zoomPercent = fitPercent × zoomLevel', () => {
    const z = make()
    z.fitPercent.value = 50
    z.setZoom(2)
    expect(z.zoomPercent.value).toBe(100)
  })
})

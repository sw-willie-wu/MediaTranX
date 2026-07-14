import { describe, it, expect, afterEach, vi } from 'vitest'

// dev 案例會真的 resolve /pipeline 的 lazy component——PipelineView 頂層 import
// @vue-flow/core，jsdom 下求值慢且有 flake 風險，mock 掉（guard 邏輯與元件無關）
vi.mock('@/views/PipelineView.vue', () => ({ default: { template: '<div/>' } }))

import router from '@/router'

const w = window as unknown as { electron?: { updateChannel?: string | null } }

afterEach(async () => { delete w.electron; await router.push('/') })

describe('/pipeline route gate（v1.7.0 已拆——任何通道皆可進）', () => {
  it('stable：可進 /pipeline（gate 已拆）', async () => {
    w.electron = { updateChannel: 'stable' }
    await router.push('/pipeline')
    expect(router.currentRoute.value.path).toBe('/pipeline')
  })
  it('dev：可進 /pipeline', async () => {
    await router.push('/pipeline')
    expect(router.currentRoute.value.path).toBe('/pipeline')
  })
})

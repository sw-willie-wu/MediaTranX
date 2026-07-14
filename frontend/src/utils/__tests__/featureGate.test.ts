import { describe, it, expect, afterEach } from 'vitest'
import { isPipelineEnabled } from '@/utils/featureGate'

const w = window as unknown as { electron?: { updateChannel?: string | null } }

afterEach(() => { delete w.electron })

describe('isPipelineEnabled', () => {
  // v1.7.0 正式開放：不論環境/通道一律 true（1.6.x 的 channel gate 已拆）
  it('無 electron（純瀏覽器/jsdom 缺省）→ true', () => {
    delete w.electron
    expect(isPipelineEnabled()).toBe(true)
  })
  it('electron 存在、channel 缺省 → true（gate 已拆）', () => {
    w.electron = {}
    expect(isPipelineEnabled()).toBe(true)
  })
  it('channel stable → true（gate 已拆）', () => {
    w.electron = { updateChannel: 'stable' }
    expect(isPipelineEnabled()).toBe(true)
  })
})

import { describe, it, expect, afterEach } from 'vitest'
import { isPipelineEnabled } from '@/utils/featureGate'

const w = window as unknown as { electron?: { updateChannel?: string | null } }

afterEach(() => { delete w.electron })

describe('isPipelineEnabled', () => {
  it('無 electron（純瀏覽器/jsdom 缺省）→ true', () => {
    delete w.electron
    expect(isPipelineEnabled()).toBe(true)
  })
  it('electron 存在但 channel 缺省 → false（fail-safe）', () => {
    w.electron = {}
    expect(isPipelineEnabled()).toBe(false)
  })
  it('channel dev → true', () => {
    w.electron = { updateChannel: 'dev' }
    expect(isPipelineEnabled()).toBe(true)
  })
  it('channel stable → false', () => {
    w.electron = { updateChannel: 'stable' }
    expect(isPipelineEnabled()).toBe(false)
  })
})

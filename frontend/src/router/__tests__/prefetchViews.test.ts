import { describe, it, expect, vi, beforeEach } from 'vitest'
import { prefetchToolViews, _resetForTest } from '@/router/prefetchViews'

describe('prefetchToolViews', () => {
  beforeEach(() => _resetForTest())

  it('只觸發一次（once 去重）', () => {
    const loader = vi.fn().mockResolvedValue({})
    prefetchToolViews([loader])
    prefetchToolViews([loader])
    expect(loader).toHaveBeenCalledTimes(1)
  })

  it('loader reject 靜默不拋', async () => {
    const bad = vi.fn().mockRejectedValue(new Error('offline'))
    expect(() => prefetchToolViews([bad])).not.toThrow()
    await Promise.resolve()
  })

  it('loader 同步拋錯也吞掉', () => {
    const throws = vi.fn(() => { throw new Error('sync') })
    expect(() => prefetchToolViews([throws])).not.toThrow()
    expect(throws).toHaveBeenCalledTimes(1)
  })
})

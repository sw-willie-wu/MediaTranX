import { describe, it, expect } from 'vitest'

describe('vitest infra smoke', () => {
  it('runs basic assertions', () => {
    expect(1 + 1).toBe(2)
  })

  it('has access to jsdom environment', () => {
    expect(typeof window).toBe('object')
    expect(typeof document).toBe('object')
  })
})

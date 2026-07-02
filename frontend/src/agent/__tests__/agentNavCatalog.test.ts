import { describe, it, expect } from 'vitest'
import { subfunctionsForView, AGENT_NAV_CATALOG } from '@/agent/agentNavCatalog'

describe('agentNavCatalog', () => {
  it('subfunctionsForView("image") includes compress', () => {
    expect(subfunctionsForView('image')).toContain('compress')
  })

  it('subfunctionsForView("image") includes transcode', () => {
    expect(subfunctionsForView('image')).toContain('transcode')
  })

  it('subfunctionsForView("unknown") returns empty array', () => {
    expect(subfunctionsForView('nonexistent')).toEqual([])
  })

  it('image catalog entry exists', () => {
    const imageEntry = AGENT_NAV_CATALOG.find(e => e.viewId === 'image')
    expect(imageEntry).toBeDefined()
    expect(imageEntry?.subfunctions).toContain('compress')
  })
})

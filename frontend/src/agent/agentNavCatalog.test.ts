import { describe, it, expect } from 'vitest'
import { AGENT_NAV_CATALOG, subfunctionsForView, routeForView } from '@/agent/agentNavCatalog'

describe('agentNavCatalog', () => {
  it('covers all 7 navigable routes', () => {
    const routes = AGENT_NAV_CATALOG.map(e => e.route).sort()
    expect(routes).toEqual(['/', '/audio', '/document', '/image', '/settings', '/tasks', '/video'])
  })

  it('exposes verbatim subfunctions per view (matches the *View.vue literals)', () => {
    expect(subfunctionsForView('image')).toEqual(
      ['transcode','compress','adjust','filter','crop','remove-bg','ai-remove','upscale','ocr'])
    expect(subfunctionsForView('video')).toEqual(
      ['transcode','cut','crop','subtitle','summary','interpolate','enhance'])
    expect(subfunctionsForView('audio')).toEqual(
      ['transcode','cut','volume','midi-edit','transcribe','separate','lyrics'])
    expect(subfunctionsForView('document')).toEqual(['split','pdf-convert','ocr','translate'])
    expect(subfunctionsForView('settings')).toEqual(
      ['general','system','models','agent','video-download','about'])
  })

  it('returns [] for views without subfunctions and unknown ids', () => {
    expect(subfunctionsForView('tasks')).toEqual([])
    expect(subfunctionsForView('home')).toEqual([])
    expect(subfunctionsForView('nope')).toEqual([])
  })

  it('maps viewId → route (and null for unknown)', () => {
    expect(routeForView('video')).toBe('/video')
    expect(routeForView('home')).toBe('/')
    expect(routeForView('nope')).toBeNull()
  })
})

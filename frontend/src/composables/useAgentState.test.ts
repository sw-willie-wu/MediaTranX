import { describe, it, expect } from 'vitest'
import { buildAgentStateSnapshot } from '@/composables/useAgentState'
import type { PanelAgentSchema } from '@/stores/panelRegistry'

const transcodeSchema: PanelAgentSchema = {
  panelId: 'video.transcode',
  fields: [
    { name: 'output_format', type: 'enum', options: () => ['mp4', 'mkv', 'webm'] },
    { name: 'crf', type: 'number', min: 0, max: () => 51, step: 1 },
    { name: 'hidden_field', type: 'string', visibleWhen: () => false },
  ],
  actions: [{ name: 'browse', label: 'Browse' }],
  execute: { requiresConfirm: true, label: 'Transcode' },
}

describe('buildAgentStateSnapshot', () => {
  it('builds the map tier from the nav catalog + files + current position', () => {
    const snap = buildAgentStateSnapshot({
      activePanel: null,
      currentRoute: '/video',
      currentSubfunction: 'transcode',
      files: [{ id: 'f1', name: 'clip.mp4', kind: 'video' }],
      activeFile: { id: 'f1', name: 'clip.mp4', kind: 'video' },
    })
    expect(snap.map.current_position).toEqual({ view: '/video', subfunction: 'transcode' })
    expect(snap.map.files).toEqual([{ id: 'f1', name: 'clip.mp4', kind: 'video' }])
    const video = snap.map.views.find(v => v.route === '/video')!
    expect(video.subfunctions).toContain('transcode')
    expect(snap.active_panel).toBeNull()
    expect(snap.active_file).toEqual({ id: 'f1', name: 'clip.mp4', kind: 'video' })
  })

  it('materializes lazy field getters into the active_panel detail tier', () => {
    const snap = buildAgentStateSnapshot({
      activePanel: {
        panelId: 'video.transcode',
        schema: transcodeSchema,
        currentValues: { output_format: 'mp4', crf: 23, hidden_field: '' },
      },
      currentRoute: '/video',
      currentSubfunction: 'transcode',
      files: [],
      activeFile: null,
    })
    const ap = snap.active_panel!
    expect(ap.panel_id).toBe('video.transcode')
    const fmt = ap.fields.find(f => f.name === 'output_format')!
    expect(fmt.options).toEqual(['mp4', 'mkv', 'webm'])
    expect(fmt.current_value).toBe('mp4')
    const crf = ap.fields.find(f => f.name === 'crf')!
    expect(crf.min).toBe(0)
    expect(crf.max).toBe(51)
    expect(crf.current_value).toBe(23)
    const hidden = ap.fields.find(f => f.name === 'hidden_field')!
    expect(hidden.visible).toBe(false)
    expect(ap.execute).toEqual({ requires_confirm: true, label: 'Transcode' })
    expect(ap.actions).toEqual([{ name: 'browse', label: 'Browse' }])
  })

  it('defaults visible to true when visibleWhen is absent', () => {
    const snap = buildAgentStateSnapshot({
      activePanel: { panelId: 'p', schema: transcodeSchema, currentValues: {} },
      currentRoute: '/video', currentSubfunction: 'transcode', files: [], activeFile: null,
    })
    expect(snap.active_panel!.fields.find(f => f.name === 'output_format')!.visible).toBe(true)
  })
})

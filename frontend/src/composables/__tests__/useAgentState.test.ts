/**
 * Tests for useAgentState — buildAgentStateSnapshot (Task 0.2)
 *
 * Covers:
 *   1. field.description in PanelFieldSchema 傳遞進 snapshot 的 SnapshotField
 *   2. 無 description 的欄位 snapshot 不帶該 key
 */
import { describe, it, expect } from 'vitest'
import { buildAgentStateSnapshot, type SnapshotInputs } from '../useAgentState'
import type { PanelAgentSchema } from '@/stores/panelRegistry'

function makeSchema(fields: PanelAgentSchema['fields']): PanelAgentSchema {
  return {
    panelId: 'image.upscale',
    fields,
    actions: [],
    execute: null,
  }
}

function makeInputs(schema: PanelAgentSchema, currentValues: Record<string, unknown>): SnapshotInputs {
  return {
    activePanel: { panelId: schema.panelId, schema, currentValues },
    currentRoute: null,
    currentSubfunction: null,
    files: [],
    activeFile: null,
  }
}

describe('buildAgentStateSnapshot — field description passthrough', () => {
  it('field.description 傳遞進 snapshot 對應欄位', () => {
    const schema = makeSchema([
      { name: 'scale', type: 'number', description: 'hint' },
    ])
    const snapshot = buildAgentStateSnapshot(makeInputs(schema, { scale: 2 }))
    const field = snapshot.active_panel!.fields.find(f => f.name === 'scale')
    expect(field?.description).toBe('hint')
  })

  it('無 description 的欄位 snapshot 不帶該 key', () => {
    const schema = makeSchema([
      { name: 'model', type: 'enum', options: () => ['a', 'b'] },
    ])
    const snapshot = buildAgentStateSnapshot(makeInputs(schema, { model: 'a' }))
    const field = snapshot.active_panel!.fields.find(f => f.name === 'model')
    expect(field).toBeDefined()
    expect('description' in (field as object)).toBe(false)
  })
})

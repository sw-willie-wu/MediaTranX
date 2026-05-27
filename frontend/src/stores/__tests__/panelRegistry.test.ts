import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { panelRegistry, type PanelHandle, type PanelAgentSchema } from '../panelRegistry'

// Clear registry between tests for isolation
beforeEach(() => {
  panelRegistry._clearAll()
})

function makeSchema(panelId: string): PanelAgentSchema {
  return {
    panelId,
    fields: [
      { name: 'model', type: 'enum', options: () => ['a', 'b'] },
      { name: 'scale', type: 'number', min: 1, max: 4 },
    ],
    actions: [{ name: 'reset', label: 'Reset' }],
    execute: { requiresConfirm: false, label: 'Start' },
  }
}

function makeHandle(panelId: string): PanelHandle {
  const values: Record<string, unknown> = { model: 'a', scale: 2 }
  const isMounted = ref(true)
  return {
    agentSchema: makeSchema(panelId),
    getCurrentValues: () => ({ ...values }),
    setField: (field, value) => { values[field] = value; return value },
    openField: (_field) => {},
    execute: async () => ({ task_id: 'task-123' }),
    invokeAction: (_name) => {},
    isMultiSelect: () => false,
    isMounted,
  }
}

describe('panelRegistry', () => {
  it('register + get returns the registered handle', () => {
    const handle = makeHandle('image-upscale')
    panelRegistry.register('image-upscale', handle)
    expect(panelRegistry.get('image-upscale')).toBe(handle)
  })

  it('get returns undefined for unknown panelId', () => {
    expect(panelRegistry.get('nonexistent')).toBeUndefined()
  })

  it('unregister removes the handle', () => {
    panelRegistry.register('audio-transcribe', makeHandle('audio-transcribe'))
    panelRegistry.unregister('audio-transcribe')
    expect(panelRegistry.get('audio-transcribe')).toBeUndefined()
  })

  it('unregister on unknown id is a no-op (no error)', () => {
    expect(() => panelRegistry.unregister('ghost-panel')).not.toThrow()
  })

  it('registering the same id twice overwrites the previous handle', () => {
    const h1 = makeHandle('vid')
    const h2 = makeHandle('vid')
    panelRegistry.register('vid', h1)
    panelRegistry.register('vid', h2)
    expect(panelRegistry.get('vid')).toBe(h2)
  })

  it('agentSchema is accessible on retrieved handle', () => {
    const handle = makeHandle('image-upscale')
    panelRegistry.register('image-upscale', handle)
    const retrieved = panelRegistry.get('image-upscale')!
    expect(retrieved.agentSchema.panelId).toBe('image-upscale')
    expect(retrieved.agentSchema.fields).toHaveLength(2)
    expect(retrieved.agentSchema.actions).toHaveLength(1)
    expect(retrieved.agentSchema.execute).not.toBeNull()
  })

  it('getCurrentValues returns current field values', () => {
    const handle = makeHandle('image-upscale')
    panelRegistry.register('image-upscale', handle)
    const vals = panelRegistry.get('image-upscale')!.getCurrentValues()
    expect(vals.model).toBe('a')
    expect(vals.scale).toBe(2)
  })

  it('setField updates the value', () => {
    const handle = makeHandle('image-upscale')
    panelRegistry.register('image-upscale', handle)
    panelRegistry.get('image-upscale')!.setField('model', 'b')
    expect(panelRegistry.get('image-upscale')!.getCurrentValues().model).toBe('b')
  })

  it('execute resolves with task_id', async () => {
    const handle = makeHandle('image-upscale')
    panelRegistry.register('image-upscale', handle)
    const result = await panelRegistry.get('image-upscale')!.execute()
    expect(result.task_id).toBe('task-123')
  })

  it('isMounted is a reactive ref', () => {
    const handle = makeHandle('video-panel')
    panelRegistry.register('video-panel', handle)
    expect(panelRegistry.get('video-panel')!.isMounted.value).toBe(true)
    handle.isMounted.value = false
    expect(panelRegistry.get('video-panel')!.isMounted.value).toBe(false)
  })

  it('multiple panels coexist independently', () => {
    const h1 = makeHandle('p1')
    const h2 = makeHandle('p2')
    panelRegistry.register('p1', h1)
    panelRegistry.register('p2', h2)
    panelRegistry.get('p1')!.setField('scale', 4)
    expect(panelRegistry.get('p1')!.getCurrentValues().scale).toBe(4)
    expect(panelRegistry.get('p2')!.getCurrentValues().scale).toBe(2)
  })

  it('null execute is allowed for settings-only panels', () => {
    const handle = makeHandle('settings-panel')
    handle.agentSchema.execute = null
    panelRegistry.register('settings-panel', handle)
    expect(panelRegistry.get('settings-panel')!.agentSchema.execute).toBeNull()
  })

  it('_clearAll removes all entries', () => {
    panelRegistry.register('a', makeHandle('a'))
    panelRegistry.register('b', makeHandle('b'))
    panelRegistry._clearAll()
    expect(panelRegistry.get('a')).toBeUndefined()
    expect(panelRegistry.get('b')).toBeUndefined()
  })
})

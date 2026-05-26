import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { viewRegistry, type ViewHandle } from '../viewRegistry'

// Clear registry between tests for isolation
beforeEach(() => {
  viewRegistry._clearAll()
})

function makeHandle(initialFn = 'tab1'): ViewHandle {
  const currentFunction = ref(initialFn)
  return {
    currentFunction,
    setCurrentFunction: (id: string) => { currentFunction.value = id },
  }
}

describe('viewRegistry', () => {
  it('register + get returns the registered handle', () => {
    const handle = makeHandle('tab1')
    viewRegistry.register('audio', handle)
    expect(viewRegistry.get('audio')).toBe(handle)
  })

  it('get returns undefined for unknown viewId', () => {
    expect(viewRegistry.get('nonexistent')).toBeUndefined()
  })

  it('unregister removes the handle', () => {
    const handle = makeHandle()
    viewRegistry.register('video', handle)
    viewRegistry.unregister('video')
    expect(viewRegistry.get('video')).toBeUndefined()
  })

  it('unregister on unknown id is a no-op (no error)', () => {
    expect(() => viewRegistry.unregister('ghost')).not.toThrow()
  })

  it('registering the same id twice overwrites the previous handle', () => {
    const h1 = makeHandle('a')
    const h2 = makeHandle('b')
    viewRegistry.register('shared', h1)
    viewRegistry.register('shared', h2)
    expect(viewRegistry.get('shared')).toBe(h2)
  })

  it('setCurrentFunction on retrieved handle mutates the reactive ref', () => {
    const handle = makeHandle('initial')
    viewRegistry.register('image', handle)
    viewRegistry.get('image')!.setCurrentFunction('face_restore')
    expect(handle.currentFunction.value).toBe('face_restore')
  })

  it('multiple views can coexist independently', () => {
    const h1 = makeHandle('fn1')
    const h2 = makeHandle('fn2')
    viewRegistry.register('v1', h1)
    viewRegistry.register('v2', h2)
    viewRegistry.get('v1')!.setCurrentFunction('changed')
    expect(viewRegistry.get('v1')!.currentFunction.value).toBe('changed')
    expect(viewRegistry.get('v2')!.currentFunction.value).toBe('fn2')
  })

  it('_clearAll removes all entries', () => {
    viewRegistry.register('a', makeHandle())
    viewRegistry.register('b', makeHandle())
    viewRegistry._clearAll()
    expect(viewRegistry.get('a')).toBeUndefined()
    expect(viewRegistry.get('b')).toBeUndefined()
  })
})

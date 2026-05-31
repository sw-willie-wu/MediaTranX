/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect } from 'vitest'
import { normalizeToolCallArgs, pickAssistant, sanitizeAssistantMessage } from '@/composables/agentSanitize'

describe('normalizeToolCallArgs', () => {
  it('valid JSON → unchanged', () => {
    expect(normalizeToolCallArgs('{"a":1}')).toBe('{"a":1}')
  })
  it('empty string → "{}"', () => {
    expect(normalizeToolCallArgs('')).toBe('{}')
    expect(normalizeToolCallArgs('   ')).toBe('{}')
  })
  it('truncated "{" → "{}"', () => {
    expect(normalizeToolCallArgs('{')).toBe('{}')
  })
  it('garbage → "{}"', () => {
    expect(normalizeToolCallArgs('not json at all')).toBe('{}')
  })
})

describe('pickAssistant', () => {
  it('returns last assistant message', () => {
    const msgs = [
      { id: 'a', role: 'assistant', content: 'first' },
      { id: 'u', role: 'user', content: 'mid' },
      { id: 'b', role: 'assistant', content: 'last' },
    ] as any
    expect(pickAssistant(msgs)?.id).toBe('b')
  })
  it('no assistant → undefined', () => {
    expect(pickAssistant([{ id: 'u', role: 'user', content: 'x' }] as any)).toBeUndefined()
    expect(pickAssistant([])).toBeUndefined()
  })
})

describe('sanitizeAssistantMessage', () => {
  it('undefined → null', () => {
    expect(sanitizeAssistantMessage(undefined)).toBeNull()
  })
  it('filters empty-name tool calls (Bug #9)', () => {
    const raw = {
      id: 'm1', role: 'assistant', content: 'ok',
      toolCalls: [
        { id: 'tc_phantom', type: 'function', function: { name: '', arguments: '' } },
        { id: 'tc_real', type: 'function', function: { name: 'navigate_to', arguments: '{"route":"image"}' } },
      ],
    } as any
    const out = sanitizeAssistantMessage(raw)!
    expect(out.toolCalls).toHaveLength(1)
    expect(out.toolCalls[0].function.name).toBe('navigate_to')
  })
  it('normalizes truncated/empty args to "{}"', () => {
    const raw = {
      id: 'm1', role: 'assistant', content: '',
      toolCalls: [
        { id: 'tc1', type: 'function', function: { name: 'set_field', arguments: '{' } },
        { id: 'tc2', type: 'function', function: { name: 'set_field', arguments: '' } },
      ],
    } as any
    const out = sanitizeAssistantMessage(raw)!
    expect(out.toolCalls[0].function.arguments).toBe('{}')
    expect(out.toolCalls[1].function.arguments).toBe('{}')
  })
  it('missing id/content → defaults', () => {
    const out = sanitizeAssistantMessage({ role: 'assistant', toolCalls: [] } as any)!
    expect(typeof out.id).toBe('string')
    expect(out.content).toBe('')
    expect(out.toolCalls).toEqual([])
  })
  it('preserves type:function on kept tool calls', () => {
    const raw = { id: 'm1', role: 'assistant', content: '', toolCalls: [
      { id: 'tc1', type: 'function', function: { name: 'click_execute', arguments: '{}' } },
    ] } as any
    const out = sanitizeAssistantMessage(raw)!
    expect(out.toolCalls[0].type).toBe('function')
  })
})

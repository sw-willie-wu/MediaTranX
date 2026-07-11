// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getTools, dispatch, type ToolCall } from '@/composables/useAgentTools'

const w = window as unknown as { electron?: { updateChannel?: string | null } }
const PIPELINE_TOOLS = ['create_pipeline', 'run_pipeline']

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => { delete w.electron })

describe('useAgentTools — pipeline gate', () => {
  it('dev（缺省）：getTools 含兩個 pipeline 工具且列於清單尾端（順序不變）', () => {
    const names = getTools(null).map(t => t.name)
    expect(names).toEqual(expect.arrayContaining(PIPELINE_TOOLS))
    expect(names.slice(-2)).toEqual(PIPELINE_TOOLS)
  })

  it('stable：getTools 不含 pipeline 工具、其餘順序不變', () => {
    const devNames = getTools(null).map(t => t.name)
    w.electron = { updateChannel: 'stable' }
    const stableNames = getTools(null).map(t => t.name)
    expect(stableNames).toEqual(devNames.filter(n => !PIPELINE_TOOLS.includes(n)))
  })

  it('stable：dispatch create_pipeline 回 gate error（帶合法 nodes/edges 過 required 前置檢查）', async () => {
    w.electron = { updateChannel: 'stable' }
    // ToolCall 真實形狀：dispatch 讀 tc.function.name / tc.function.arguments（JSON 字串）
    const call: ToolCall = {
      id: 'tc-1',
      type: 'function',
      function: {
        name: 'create_pipeline',
        arguments: JSON.stringify({
          nodes: [{ id: 'a', kind: 'input' }, { id: 'b', kind: 'tool', tool_key: 'image.convert' }],
          edges: [{ from: 'a', to: 'b' }],
        }),
      },
    }
    const res = await dispatch(call)
    expect(res.error).toBe('agent.error.tool_failed')
    expect(String(res.detail ?? '')).toContain('pipeline disabled')
  })

  it('stable：dispatch run_pipeline 回 gate error', async () => {
    w.electron = { updateChannel: 'stable' }
    const call: ToolCall = {
      id: 'tc-2',
      type: 'function',
      function: { name: 'run_pipeline', arguments: JSON.stringify({}) },
    }
    const res = await dispatch(call)
    expect(res.error).toBe('agent.error.tool_failed')
    expect(String(res.detail ?? '')).toContain('pipeline disabled')
  })
})

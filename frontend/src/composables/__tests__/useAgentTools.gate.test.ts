// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getTools } from '@/composables/useAgentTools'

const w = window as unknown as { electron?: { updateChannel?: string | null } }
const PIPELINE_TOOLS = ['create_pipeline', 'run_pipeline']

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => { delete w.electron })

describe('useAgentTools — pipeline gate（v1.7.0 已拆，任何通道皆宣告）', () => {
  it('缺省（無 electron）：getTools 含兩個 pipeline 工具且列於清單尾端', () => {
    const names = getTools(null).map(t => t.name)
    expect(names).toEqual(expect.arrayContaining(PIPELINE_TOOLS))
    expect(names.slice(-2)).toEqual(PIPELINE_TOOLS)
  })

  it('stable：getTools 同樣宣告 pipeline 工具（gate 已拆、與 dev 清單一致）', () => {
    const devNames = getTools(null).map(t => t.name)
    w.electron = { updateChannel: 'stable' }
    const stableNames = getTools(null).map(t => t.name)
    expect(stableNames).toEqual(devNames)
  })
})

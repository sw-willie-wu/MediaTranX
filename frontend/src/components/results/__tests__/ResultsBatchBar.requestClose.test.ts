/** @vitest-environment jsdom */
/** v1.7.1 G — 批次「加入工具」也先 emit request-close（對稱 ResultCard）。 */
import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const openManyInTool = vi.fn().mockResolvedValue(undefined)
const clearSelection = vi.fn()
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ path: '/image' }) }))
vi.mock('@/composables/useConfirm', () => ({ useConfirm: () => ({ confirm: vi.fn() }) }))
vi.mock('@/stores/results', () => ({
  useResultsStore: () => ({
    selectedIds: new Set(['a', 'b']),
    selectedCategory: 'image',
    openManyInTool,
    clearSelection,
    saveBatch: vi.fn(), deleteBatch: vi.fn(),
  }),
}))

import ResultsBatchBar from '@/components/results/ResultsBatchBar.vue'

describe('ResultsBatchBar — 批次加入工具即關抽屜', () => {
  it('點批次「加入工具」→ emit request-close 且呼叫 openManyInTool', async () => {
    const w = mount(ResultsBatchBar)
    const btn = w.findAll('button').find((b) => b.text().includes('batch_open'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('request-close')).toHaveLength(1)
    await flushPromises()
    expect(openManyInTool).toHaveBeenCalledWith(['a', 'b'], expect.anything(), '/image')
  })
})

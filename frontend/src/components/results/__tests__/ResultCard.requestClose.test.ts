/** @vitest-environment jsdom */
/**
 * v1.7.1 G — 「加入對應的媒體工具」按下時先 emit request-close（關抽屜給即時體感），
 * 再呼叫 store.openInTool（fire-and-forget，不阻擋）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const openInTool = vi.fn()
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ path: '/image' }) }))
vi.mock('@/composables/useToolLabel', () => ({ useToolLabel: () => ({ toolLabel: (x: string) => x }) }))
vi.mock('@/stores/results', () => ({
  useResultsStore: () => ({
    selectedIds: new Set<string>(),
    savingIds: new Set<string>(),
    openInTool,
    toggleSelect: vi.fn(), previewOne: vi.fn(), saveOne: vi.fn(), browseSaved: vi.fn(), removeOne: vi.fn(),
  }),
}))

import ResultCard from '@/components/results/ResultCard.vue'

const entry = {
  fileId: 'img1', filename: 'out.png', fileSize: 100, mimeType: 'image/png',
  toolId: 'image.convert', savedPath: null,
} as any

describe('ResultCard — 加入工具即關抽屜', () => {
  it('點「加入工具」→ emit request-close 且呼叫 openInTool', async () => {
    const w = mount(ResultCard, { props: { entry } })
    const btn = w.findAll('button').find((b) => b.text().includes('add_to_tool'))
    expect(btn).toBeTruthy()
    await btn!.trigger('click')
    expect(w.emitted('request-close')).toHaveLength(1)
    expect(openInTool).toHaveBeenCalledWith('img1', expect.anything(), '/image')
  })
})

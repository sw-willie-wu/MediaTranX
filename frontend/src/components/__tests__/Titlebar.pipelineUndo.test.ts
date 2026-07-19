/** @vitest-environment jsdom */
/**
 * 流程頁 titlebar 必須渲染 undo/redo 鈕（畫布 UX 批次已接 registerActions，
 * 但渲染 gate 原只認 isToolPage、/pipeline 不在 toolTitleKeys → 按鈕從未出現）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const routePath = { path: '/pipeline' }
vi.mock('vue-router', () => ({ useRoute: () => routePath }))
vi.mock('vue-i18n', async (orig) => {
  const mod = await orig<typeof import('vue-i18n')>()
  return { ...mod, useI18n: () => ({ t: (k: string) => k }) }
})

import Titlebar from '@/components/Titlebar.vue'
import TitlebarButton from '@/components/common/TitlebarButton.vue'

const STUBS = {
  TitlebarResultsButton: true,
  TitlebarChatBubbleButton: true,
}

function tooltipsAt(path: string): string[] {
  routePath.path = path
  const w = mount(Titlebar, {
    global: { stubs: STUBS, mocks: { $t: (k: string) => k } },
  })
  return w.findAllComponents(TitlebarButton).map((b) => b.props('tooltip') as string)
}

describe('Titlebar — undo/redo 渲染 gate', () => {
  it('流程頁（/pipeline）渲染 undo/redo 鈕', () => {
    const tips = tooltipsAt('/pipeline')
    expect(tips).toContain('titlebar.undo')
    expect(tips).toContain('titlebar.redo')
  })

  it('工具頁（/image）仍渲染 undo/redo 鈕（不回歸）', () => {
    const tips = tooltipsAt('/image')
    expect(tips).toContain('titlebar.undo')
    expect(tips).toContain('titlebar.redo')
  })

  it('非工具頁（/settings）不渲染 undo/redo 鈕', () => {
    const tips = tooltipsAt('/settings')
    expect(tips).not.toContain('titlebar.undo')
    expect(tips).not.toContain('titlebar.redo')
  })
})

// @vitest-environment jsdom
/**
 * UnsupportedFileOverlay——unsupported/flow-file 兩 variant（spec §4.3）＋i18n 化驗證。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import UnsupportedFileOverlay from '@/components/UnsupportedFileOverlay.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      unsupported: {
        title: 'This tool does not support this file format',
        goto: 'Open in {tool}',
        close: 'Close',
        flow_file: 'This is a MediaTranX flow file',
        open_in_pipeline: 'Open in Pipeline',
      },
    },
  },
})

function mountOverlay(props: Record<string, unknown>) {
  return mount(UnsupportedFileOverlay, { props: { visible: true, target: null, ...props }, global: { plugins: [i18n] } })
}

describe('UnsupportedFileOverlay', () => {
  it('預設 unsupported 變體：警示 icon＋title；target 有值才顯示前往鈕', () => {
    const w = mountOverlay({ target: 'video' })
    expect(w.find('.bi-exclamation-triangle').exists()).toBe(true)
    expect(w.text()).toContain('does not support')
    expect(w.find('.goto-btn').exists()).toBe(true)
    const w2 = mountOverlay({ target: null })
    expect(w2.find('.goto-btn').exists()).toBe(false)
  })

  it('flow-file 變體：流程 icon＋流程檔文案＋「前往流程頁開啟」（target 為 null 仍顯示）', () => {
    const w = mountOverlay({ target: null, mode: 'flow-file' })
    expect(w.find('.bi-diagram-3').exists()).toBe(true)
    expect(w.text()).toContain('flow file')
    expect(w.find('.goto-btn').text()).toBe('Open in Pipeline')
  })

  it('goto/dismiss 事件', async () => {
    const w = mountOverlay({ target: null, mode: 'flow-file' })
    await w.find('.goto-btn').trigger('click')
    expect(w.emitted('goToTool')).toBeTruthy()
    await w.find('.dismiss-btn').trigger('click')
    expect(w.emitted('dismiss')).toBeTruthy()
  })

  it('visible=false 不渲染', () => {
    const w = mountOverlay({ visible: false })
    expect(w.find('.unsupported-overlay').exists()).toBe(false)
  })
})

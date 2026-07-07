import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import AppUploadZone from '@/components/common/AppUploadZone.vue'
import en from '@/i18n/locales/en'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const mountOpts = { global: { plugins: [i18n] } }

function fakeFolderFile(name: string, relPath: string): File {
  const f = new File(['x'], name, { type: 'image/png' })
  Object.defineProperty(f, 'webkitRelativePath', { value: relPath })
  return f
}

describe('AppUploadZone folder picker', () => {
  it('renders the folder link with i18n label', () => {
    const w = mount(AppUploadZone, mountOpts)
    const link = w.find('.folder-link')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('or select a folder')
  })

  it('clicking the link opens the folder input only (not the file input)', async () => {
    const w = mount(AppUploadZone, mountOpts)
    const inputs = w.findAll('input')
    expect(inputs).toHaveLength(2) // [0] 檔案 input、[1] 資料夾 input
    // 只 mock 檔案 input 的 click;資料夾 input 的 click 保持真實 dispatch,
    // 讓它的合成 click 事件真的冒泡——真機 bug:folderInput.click() 的事件
    // 冒泡回 .upload-zone 的 handleClick → fileInput.click() → 連開兩個對話框。
    // (mock 掉 folder click 會遮蔽這條路徑,之前就是這樣漏掉的)
    const fileClick = vi.spyOn(inputs[0].element, 'click').mockImplementation(() => {})
    const folderClickSeen = vi.fn()
    inputs[1].element.addEventListener('click', folderClickSeen)
    await w.find('.folder-link').trigger('click')
    expect(folderClickSeen).toHaveBeenCalledTimes(1)
    expect(fileClick).not.toHaveBeenCalled() // 連結冒泡與 input 合成 click 冒泡都不得觸發選檔
  })

  it('folder input change emits folder-files with capped files', async () => {
    const w = mount(AppUploadZone, mountOpts)
    const folderInput = w.findAll('input')[1]
    const a = fakeFolderFile('a.png', 'r/a.png')
    const b = fakeFolderFile('b.png', 'r/sub/b.png')
    // jsdom 的 input.files 唯讀 → defineProperty 塞 array-like
    // (handleFolderInput 只用 .length 與 Array.from,array 即可)
    Object.defineProperty(folderInput.element, 'files', { value: [a, b] })
    await folderInput.trigger('change')
    const emitted = w.emitted('folder-files')
    expect(emitted).toHaveLength(1)
    expect(emitted![0][0]).toEqual([a, b])
    expect(emitted![0][1]).toBe(false)
  })

  it('folder input change with zero files is a silent no-op', async () => {
    const w = mount(AppUploadZone, mountOpts)
    const folderInput = w.findAll('input')[1]
    Object.defineProperty(folderInput.element, 'files', { value: [] })
    await folderInput.trigger('change')
    expect(w.emitted('folder-files')).toBeUndefined()
  })
})

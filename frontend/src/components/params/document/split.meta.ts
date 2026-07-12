/**
 * document.split 參數 META（統一參數元件 spec §4；批 4 Task 4.5 Part A）。
 * schema 準繩＝後端 DocumentSplitRequest 全集（backend/app/api/routes/document/split.py）：
 * pages:str=''（file_id/suppress_results 由 host 注入，不入 schema）。
 *
 * ⚠ seedOnFileChange 觸發源特例：舊 DocumentSplitPanel.vue 用
 * `watch(() => props.fileId, () => { pages.value = '' })`——換檔（含切到/離開無檔案）無條件
 * 清空，不比較新舊 fileId 內容。ToolParamHost 的 seed 觸發源固定綁 `fileInfo` prop（immediate
 * watch），非 fileId；但 document 領域目前沒有 /document/info 這類 fetch（見
 * useDocumentWorkspace.ts，無 mediaInfo/imageInfo 對應物），無法比照 video/audio/image 三域
 * 直接餵一個「真」info 物件。
 *
 * 因此 DocumentView.vue 的 document.split 掛載點改餵一個以 fileId 為內容的最小合成物件
 * （`fileId ? { fileId } : null`）——純粹製造「fileId 變了 → 物件參考變了 → watch 觸發」的
 * reactivity 訊號，不代表真的有檔案 info 通道。下方 seedOnFileChange 本身不讀取傳入內容
 * （兩參數皆加底線標記未使用），只要被呼叫就無條件回傳 `{ pages: '' }`，語意與舊 watch
 * 完全等價（含初次掛載的 immediate 呼叫——當時 pages 已是預設空字串，重複清空無副作用）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'document.split',
  apiPath: '/document/split',
  labelKey: 'document.split.task_label',
  taskType: 'document.split',
  schema: [
    { name: 'pages', type: 'string', default: '' },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // 舊 View.handleMultiExecute 的 'split' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 DocumentSplitPanel.agentSchema.execute：{requiresConfirm:false,label:'panel.doc_split.execute'}。
  agentRequiresConfirm: false,
  agentExecuteLabel: 'panel.doc_split.execute',
  // 見檔頭註解：不讀取傳入內容，僅利用「被呼叫」這件事清空 pages。
  seedOnFileChange(_fileInfo, _current) {
    return { pages: '' }
  },
}

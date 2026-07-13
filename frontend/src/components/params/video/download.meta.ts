/**
 * video.download 參數 META（統一參數元件 spec §4；批 2 Task 2.2）。
 * schema 準繩＝後端 DownloadRequest（backend/app/schemas/video_download.py）：
 * url:str 必填；title:str="video"（來自 probe 卡，後端做檔名 sanitize）；
 * format_intent:FormatIntent=Field(default_factory=FormatIntent)（巢狀物件，
 * mode:Literal['auto','cap','ask']='auto'、max_height:Optional[int]、format_id:Optional[str]）；
 * file_id/suppress_results 由 host/runner 注入，不入 schema。
 *
 * 範圍特例：video.download 是 registry 唯一 kind:'source' 節點（無輸入、pipeline 專用）。
 * 工具頁的下載走全域彈窗 UrlDownloadCard.vue（App.vue 根層、兩段式 probe/download），
 * 與本 META／DownloadParams.vue 無關——不接 ToolParamHost，無 seedOnFileChange（source
 * 節點無檔案可換）、無 modelRequirement（不需模型）。
 *
 * 現行 registry paramSchema（批 2 前）把 format_intent 誤建成 scalar enum
 * ['auto','video','audio']，與後端巢狀物件不符、有 422 風險——本 task 以後端為準修正，
 * registry 改組裝式（paramSchema: META.schema）。
 *
 * format_intent 不設 agentHint：dict 型欄位不曝給 ToolParamHost 的 agent set_field 介面
 * （agent 用 create_pipeline 走 dict 全量帶入，見 registry.ts 檔頭註記）——video.download
 * 本就不接 ToolParamHost，這裡沿既有建模慣例維持一致，非本 task 新規則。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'video.download',
  apiPath: '/video/download',
  labelKey: 'video.download.task_label',
  taskType: 'video.download',
  schema: [
    { name: 'url', type: 'string' },
    { name: 'title', type: 'string', default: 'video', advanced: true },
    { name: 'format_intent', type: 'dict', default: { mode: 'auto' }, advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // 必填語意靠 validate（url 無 default）：空字串/純空白/非 http(s) 開頭一律擋。
  validate(params) {
    const url = String(params.url ?? '').trim()
    if (!url || !/^https?:\/\//i.test(url)) return 'video.download.url_error'
    return null
  },
  multiSelect: false,
  // 無 seedOnFileChange（source 節點無檔案）、無 modelRequirement（不需模型）——刻意省略。
}

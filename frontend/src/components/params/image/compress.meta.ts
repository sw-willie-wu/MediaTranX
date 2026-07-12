/**
 * image.compress 參數 META（統一參數元件 spec §4；批 4 Task 4.1）。
 * schema 準繩＝後端 ImageCompressRequest（backend/app/api/routes/image/*.py）全集：
 * strength/gif_colors/gif_frame_drop/gif_optimize_transparency/png_lossy/jpeg_progressive/
 * jpeg_keep_metadata/webp_lossless（file_id/suppress_results 由 host 注入，不入 schema）。
 *
 * ⚠ strength default 三方不一致（批 4 地面實況 Surprise 4）：舊 ImageCompressPanel.vue UI
 * 初值＝75，後端 ImageCompressRequest.strength 與舊 registry 手寫 paramSchema 皆＝60。
 * 沿 video.interpolate（v4.22→v4.26 壓）先例的裁決：以「舊工具頁 UI 初值」為準保 tool 頁
 * parity（使用者不會感受到工具頁初值突然變化），pipeline 節點初值隨之從 60 變 75——此為
 * 本 task 刻意偏離後端 default 的決策，非疏漏，見 batch4-recon.md §1 Surprise 4。
 *
 * gif_frame_drop 型別（批 4 Surprise 12 裁決）：舊 panel/agentSchema 曾把它當 enum
 * ['0','2','3','4']，但後端／registry 手寫皆是 number（ge=0）。統一參數元件案「schema
 * 準繩＝後端」——改回 number，UI 用 AppSelect 呈現 0/2/3/4 四個離散值（UI 衍生，非 schema
 * enum）。連帶影響：host 自動衍生的 agent 欄位型別也從 enum 變成 number（agent 面板
 * set_field 收數字而非字串），這是本 task 刻意的行為變更，非疏漏。
 *
 * png_lossy vs 舊 png_mode（批 4 Surprise 12 附帶決策）：舊 panel 的 agentSchema 曝的是
 * png_mode（enum 'lossy'|'lossless'），但實際送後端的欄位是 png_lossy（bool）——兩者中間
 * 有一層舊 panel 自己的 setField 轉換。統一參數元件案的 agent 欄位 1:1 衍生自 meta.schema
 * （見 ToolParamHost.vue agentFields），故 agent 面板改直接曝 png_lossy（bool），UI 層
 * （CompressParams.vue）另外把它包成 png_mode 下拉（UI 衍生），agent 端不再看到 png_mode。
 *
 * 格式相依欄位可見性（GIF/PNG/JPEG/WEBP 各自的進階區）依賴 fileInfo.format，但
 * ToolParamMeta.schema[].visibleWhen 簽章只收 params（無 fileInfo）——這組欄位無法透過
 * meta 層 visibleWhen 表達格式相依可見性，故本 task 不對這些欄位設 visibleWhen（agent 面板
 * 因此會看到全部進階欄位，不會依格式收斂；工具頁 UI 由 CompressParams.vue 自行依
 * props.fileInfo.format 判斷 SettingsCollapsible 顯隱，UI 呈現不受影響）。此為與舊 panel
 * 的 agentSchema.fields[].visibleWhen（曾依 imageInfo 收斂）的已知行為差異，report 記為
 * concern，不在本 task 範圍內解（需要 host/types 擴充 visibleWhen 簽章才能修）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'image.compress',
  apiPath: '/image/compress',
  labelKey: 'image.compress.task_label',
  taskType: 'image.compress',
  schema: [
    { name: 'strength', type: 'number', min: 1, max: 100, step: 1, default: 75 },
    { name: 'gif_colors', type: 'number', min: 2, max: 256, step: 1, advanced: true },
    { name: 'gif_frame_drop', type: 'number', min: 0, step: 1, default: 0, advanced: true },
    { name: 'gif_optimize_transparency', type: 'boolean', default: true, advanced: true },
    { name: 'png_lossy', type: 'boolean', default: true, advanced: true },
    { name: 'jpeg_progressive', type: 'boolean', default: true, advanced: true },
    { name: 'jpeg_keep_metadata', type: 'boolean', default: false, advanced: true },
    { name: 'webp_lossless', type: 'boolean', default: false, advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  agentExecuteLabel: 'panel.compress.execute',
  multiSelect: true,
}

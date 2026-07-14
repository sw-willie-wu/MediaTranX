/**
 * video.interpolate 參數 META（統一參數元件 spec §4；批 2 Task 2.3——host modelRequirement
 * variant 型擴充「首用」之一，另一為 enhance.meta.ts）。
 * schema 準繩＝後端 InterpolateRequest（backend/app/api/routes/video/interpolate.py）全集。
 *
 * 後端 model default 'v4.22' 已過時——模型倉庫（backend/app/adapters/ai/registry.py，
 * category='interpolate'、family='rife'）僅提供 'v4.26' 一個 variant，registry.ts 舊
 * paramSchema／舊 VideoInterpolatePanel 皆壓 v4.26 default；此處沿用同一收斂,enum 僅列
 * v4.26（若未來新增 variant，此列表與 modelStore 實際清單會脫節——picker 用 composite
 * 覆蓋走即時清單，schema enum 僅供 pipeline 節點表單/agent 無 composite 時的靜態選項)。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'video.interpolate',
  apiPath: '/video/interpolate',
  labelKey: 'video.interpolate.task_label',
  taskType: 'video.interpolate',
  schema: [
    // model 標 advanced：pipeline 節點表單/agent 無 composite 覆蓋時退化顯示的靜態欄位，
    // 工具頁 InterpolateParams.vue 仍把 picker 放頂層（沿舊 panel 版面，見該檔案）。
    { name: 'model', type: 'enum', options: ['v4.26'], default: 'v4.26', advanced: true },
    { name: 'mode', type: 'enum', options: ['2x', '4x', 'custom'], default: '2x' },
    { name: 'target_fps', type: 'number', min: 2, max: 240, step: 1, default: 60, visibleWhen: (p) => p.mode === 'custom' },
    { name: 'output_format', type: 'enum', options: ['mp4', 'mkv', 'webm', 'mov'], default: 'mp4' },
    { name: 'video_codec', type: 'enum', options: ['h264', 'h265', 'vp9', 'av1'], default: 'h264', advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // mode!=='custom' 時剔除 target_fps——鏡射舊 VideoInterpolatePanel.getParams() 的
  // `target_fps: mode.value === 'custom' ? targetFps.value : undefined` 語意（undefined
  // 經 JSON.stringify/normalizeParams 丟棄該鍵，不殘留舊值）。
  buildSubmit(params) {
    const payload: Record<string, unknown> = { ...params }
    if (params.mode !== 'custom') delete payload.target_fps
    return {
      apiPath: this.apiPath,
      payload,
      taskType: this.taskType,
      labelKey: this.labelKey,
    }
  },
  // variant 型模型需求（批 2 Task 2.3 host 擴充首用）：RIFE 單一家族,categories 限定在
  // modelStore category='interpolate' 範圍內查找（見 modelGuardUtils.ts 檔頭註解）。
  modelRequirement(params) {
    return { slot: 'interpolate', variant: String(params.model ?? ''), categories: ['interpolate'] }
  },
  // 舊 VideoView.handleMultiExecute 的 'interpolate' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 VideoInterpolatePanel.agentSchema.execute.label 是 'panel.interpolate.execute'，
  // 與 labelKey('video.interpolate.task_label') 不同——host 沿用時需靠此欄位還原（見
  // ToolParamHost.vue agentSchema.execute 註解）。
  agentExecuteLabel: 'panel.interpolate.execute',
  persistedModelFields: ['model'],
}

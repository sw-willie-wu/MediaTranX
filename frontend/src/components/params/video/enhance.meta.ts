/**
 * video.enhance 參數 META（統一參數元件 spec §4；批 2 Task 2.3——host modelRequirement
 * variant 型擴充「首用」之一，另一為 interpolate.meta.ts）。
 * schema 準繩＝後端 EnhanceRequest（backend/app/api/routes/video/enhance.py）全集。
 *
 * 後端 model 欄位（家族，恆 'realesrgan'，前端硬編）與 variant 欄位（實際模型選擇）分離——
 * 沿舊 VideoEnhancePanel：picker 綁 variant，model 恆送 'realesrgan'。
 * variant 選項來源＝modelStore category='upscale' ∪ subcategory='video_enhance'（後端
 * registry.py 的 animevideov3 variant 掛 subcategory='video_enhance'，其餘掛
 * category='upscale'），再過濾 family==='realesrgan'（沿舊 panel 組裝邏輯）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'video.enhance',
  apiPath: '/video/enhance',
  labelKey: 'video.enhance.task_label',
  taskType: 'video.enhance',
  schema: [
    { name: 'model', type: 'string', default: 'realesrgan', advanced: true },
    { name: 'variant', type: 'enum', options: ['x2plus', 'x4plus', 'x4plus-anime', 'animevideov3'], default: 'x4plus' },
    { name: 'output_format', type: 'enum', options: ['mp4', 'mkv', 'webm', 'mov'], default: 'mp4' },
    { name: 'video_codec', type: 'enum', options: ['h264', 'h265', 'vp9', 'av1'], default: 'h264', advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // variant 型模型需求（批 2 Task 2.3 host 擴充首用）：family 過濾收斂到 realesrgan,
  // categories 涵蓋 upscale/video_enhance 兩個 modelStore category/subcategory（見檔頭註解）。
  modelRequirement(params) {
    return {
      slot: 'enhance',
      variant: String(params.variant ?? ''),
      family: 'realesrgan',
      categories: ['upscale', 'video_enhance'],
    }
  },
  // 舊 VideoView.handleMultiExecute 的 'enhance' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 VideoEnhancePanel.agentSchema.execute.label 是 'panel.enhance.execute'，與
  // labelKey('video.enhance.task_label') 不同——見 ToolParamHost.vue agentSchema.execute 註解。
  agentExecuteLabel: 'panel.enhance.execute',
  persistedModelFields: ['variant'],
}

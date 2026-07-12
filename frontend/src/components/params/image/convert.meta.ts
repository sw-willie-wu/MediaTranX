/**
 * image.convert 參數 META（統一參數元件 spec §4；批 4 Task 4.1）。
 * schema 準繩＝後端 ImageConvertRequest（backend/app/api/routes/image/*.py）全集：
 * output_format/quality/width/height/scale/coalesce（file_id/suppress_results 由 host 注入）。
 *
 * ⭐ width/height/scale 三態互斥（批 4 地面實況 §2）：後端三欄各自獨立 Optional，但語意上
 * 互斥（要嘛按比例縮放、要嘛指定自訂寬高、要嘛保持原尺寸）。UI 層（ConvertParams.vue）用
 * resizeMode（'original'|'scale'|'custom'，UI 衍生非後端欄位）切換時已盡量互斥 commit，
 * 但 agent 可能個別呼叫 set_field（例如只設 width、不知道要清 scale）留下不一致的組合——
 * buildSubmit 在送出前做最後一道防線清理：scale 有值時剔除 width/height，否則剔除 scale
 * （鏡射舊 ImageConvertPanel.getParams() 每次呼叫都重新算三選一，本質同構）。
 *
 * panelId 裁決（Surprise 2，registry 全域唯一名不同者）：toolKey/taskType 是 image.convert，
 * 但 agent 面板 panelId 沿舊 ImageConvertPanel.agentSchema.panelId 用 'image.transcode'
 * （= ImageView subFunction id、= panelIdFor('image','transcode') 的自然產出，接線時不必
 * 特殊處理）。agent 導覽相容優先，收尾批再議正名（見 batch4-recon.md Surprise 2）。
 */
import type { SubmitSpec, ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'image.convert',
  apiPath: '/image/convert',
  labelKey: 'image.convert.task_label',
  taskType: 'image.convert',
  schema: [
    { name: 'output_format', type: 'enum', options: ['png', 'jpg', 'webp', 'gif', 'bmp'], default: 'png' },
    { name: 'quality', type: 'number', min: 1, max: 100, step: 1, default: 85, advanced: true,
      visibleWhen: (p) => ['jpg', 'webp'].includes(String(p.output_format)) },
    { name: 'width', type: 'number', min: 1, step: 1, advanced: true },
    { name: 'height', type: 'number', min: 1, step: 1, advanced: true },
    { name: 'scale', type: 'number', min: 0.1, max: 2, step: 0.05, advanced: true },
    { name: 'coalesce', type: 'boolean', default: false, advanced: true,
      visibleWhen: (p) => p.output_format === 'gif' },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  buildSubmit(params): SubmitSpec {
    const payload: Record<string, unknown> = { ...params }
    const hasScale = typeof payload.scale === 'number' && Number.isFinite(payload.scale)
    if (hasScale) {
      delete payload.width
      delete payload.height
    } else {
      delete payload.scale
    }
    return {
      apiPath: this.apiPath,
      payload,
      taskType: this.taskType,
      labelKey: this.labelKey,
    }
  },
  downloadFormatField: 'output_format',
  agentExecuteLabel: 'panel.transcode.execute',
  multiSelect: true,
}

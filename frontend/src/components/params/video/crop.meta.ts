/**
 * video.crop 參數 META（統一參數元件 spec §4；批 2 Task 2.1）。
 * schema 準繩＝後端 VideoCropRequest（backend/app/api/routes/video/crop.py:17-24）：
 * x/y default 0（ge=0）、width/height 必填（gt=0）；file_id/suppress_results 由 host 注入，不入 schema。
 * width/height min=2 是 UI 收斂約束（後端 ffmpeg 向下取偶 yuv420p，1 會取到 0 直接 ValueError；
 * 準繩=後端全集指「欄位集合」，數值約束可比後端嚴——見 registry.ts 舊註記，此處把唯一事實來源
 * 收斂進 meta，registry 改組裝式）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'video.crop',
  apiPath: '/video/crop',
  labelKey: 'video.crop.task_label',
  taskType: 'video.crop',
  schema: [
    { name: 'x', type: 'number', min: 0, step: 1, default: 0 },
    { name: 'y', type: 'number', min: 0, step: 1, default: 0 },
    // width/height 無 default——必填語意靠 validate（跨欄位：非有限正數才擋）
    { name: 'width', type: 'number', min: 2, step: 1 },
    { name: 'height', type: 'number', min: 2, step: 1 },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  validate(params) {
    const w = Number(params.width)
    const h = Number(params.height)
    if (!Number.isFinite(w) || w <= 0 || !Number.isFinite(h) || h <= 0) return 'video.crop.size_error'
    return null
  },
  multiSelect: false,
  // 語意鏡射現行 VideoView：換檔後 canvas crop rect 重畫觸發覆寫，等價於「換檔無條件重置」；
  // 不依賴 fileInfo 內容（純重置，非衍生值）——與 cut.meta 的 duration 衍生不同。
  seedOnFileChange(_fileInfo, _current) {
    return { x: 0, y: 0, width: undefined, height: undefined }
  },
}

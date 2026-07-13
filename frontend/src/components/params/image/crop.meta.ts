/**
 * image.crop 參數 META（統一參數元件 spec §4；批 4 Task 4.3）。
 * schema 準繩＝後端 ImageCropRequest（backend/app/api/routes/image/crop.py:19-26）：
 * x/y default 0（無 ge 約束，UI 沿舊 panel 收斂 min=0）、width/height 必填（gt=0）；
 * file_id/suppress_results 由 host 注入，不入 schema。
 *
 * 與 video.crop（frontend/src/components/params/video/crop.meta.ts）的唯一數值差異：
 * width/height min=1（非 video 版的 min=2）——PIL 裁切（Pillow Image.crop）無 ffmpeg
 * yuv420p 向下取偶約束，1px 合法（見 batch4-recon.md §4／舊 ImageCropPanel.vue:124,129
 * 的 :min="1"）。
 *
 * agent 欄位：舊 ImageCropPanel.vue 無 useAgentPanelHost/無 agentSchema（batch4-recon.md
 * §4「唯一無 agent 的 image 工具」）。遷移到 ToolParamHost 後會依 meta.schema 自動衍生出
 * x/y/width/height 四個 agent 欄位——這是行為新增（agent 從不能操作裁切變成可以），非疏漏。
 * 沿 video.crop 遷移先例（該工具遷移前同樣無 agent）：接受此新增，不特別壓制。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'image.crop',
  apiPath: '/image/crop',
  labelKey: 'image.crop.task_label',
  taskType: 'image.crop',
  schema: [
    { name: 'x', type: 'number', min: 0, step: 1, default: 0 },
    { name: 'y', type: 'number', min: 0, step: 1, default: 0 },
    // width/height 無 default——必填語意靠 validate（跨欄位：非有限正數才擋）
    { name: 'width', type: 'number', min: 1, step: 1 },
    { name: 'height', type: 'number', min: 1, step: 1 },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  validate(params) {
    const w = Number(params.width)
    const h = Number(params.height)
    if (!Number.isFinite(w) || w <= 0 || !Number.isFinite(h) || h <= 0) return 'image.crop.size_error'
    return null
  },
  multiSelect: false,
  // 語意鏡射現行 ImageView：換檔後 canvas crop rect 重畫觸發覆寫，等價於「換檔無條件重置」；
  // 不依賴 fileInfo 內容（純重置，非衍生值）——同 video.crop.meta 語意。
  seedOnFileChange(_fileInfo, _current) {
    return { x: 0, y: 0, width: undefined, height: undefined }
  },
}

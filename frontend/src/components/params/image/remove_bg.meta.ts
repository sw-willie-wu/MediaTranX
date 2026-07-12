/**
 * image.remove_bg 參數 META（統一參數元件 spec §4；批 4 Task 4.3）。
 * schema 準繩＝後端 ImageRemoveBgRequest 全集（backend/app/api/routes/image/remove_bg.py:19-22）：
 * mode（str default 'auto'）；file_id/suppress_results 由 host 注入，不入 schema。
 *
 * ⚠ 無 modelRequirement：舊 ImageRemoveBgPanel.vue execute() 呼叫
 * guardModelReady(true, 'image') —— 傳入字面 true，恆真 guard（rembg 自備模型權重，
 * 不走 modelStore 下載流程）。統一參數元件案的 modelRequirement/modelRequirements 語意是
 * 「需要 modelStore 追蹤下載狀態的模型」，本工具不符合，故不設，host preflight 對此工具
 * 永遠通過（等價於舊 panel 的恆真 guard，行為不變）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'image.remove_bg',
  apiPath: '/image/remove-bg',
  labelKey: 'image.remove_bg.task_label',
  taskType: 'image.remove_bg',
  schema: [
    {
      name: 'mode', type: 'enum', default: 'auto',
      options: ['auto', 'person', 'product', 'animal', 'anime'],
    },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  agentExecuteLabel: 'panel.remove_bg.execute',
  multiSelect: true,
}

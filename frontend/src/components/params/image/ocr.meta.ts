/**
 * image.ocr 參數 META（統一參數元件 spec §4；批 4 Task 4.4）。
 * schema/modelRequirement/encode/decode 全部共用 document/ocr.meta.ts 的工廠與純函式——
 * 後端 ImageOcrRequest 與 DocumentOcrRequest 欄位逐一相同（見 document/ocr.meta.ts 檔頭比對
 * 記錄），僅 toolKey/apiPath/labelKey/taskType/agentExecuteLabel 隨掛載點不同。
 * Params.vue 也共用同一份元件（document/OcrParams.vue，見該檔／PARAM_COMPONENTS 註冊）。
 */
import { buildOcrMeta, decodeModelToken, encodeModelToken } from '../document/ocr.meta'
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = buildOcrMeta({
  toolKey: 'image.ocr',
  apiPath: '/image/ocr',
  labelKey: 'image.ocr.task_label',
  taskType: 'image.ocr',
  // 舊 ImageOcrPanel.agentSchema.execute.label。
  agentExecuteLabel: 'panel.ocr.execute',
})

export { encodeModelToken, decodeModelToken }

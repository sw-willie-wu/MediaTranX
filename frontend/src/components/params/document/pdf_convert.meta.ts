/**
 * document.pdf_convert 參數 META（統一參數元件 spec §4；批 4 Task 4.5 Part B）。
 * schema 準繩＝後端 PdfConvertRequest 全集（backend/app/api/routes/document/pdf_convert.py）：
 * output_format:Literal['txt','md','images']='txt'（file_id/suppress_results 由 host 注入，
 * 不入 schema）。
 *
 * ⚠ images 僅 PDF 可用是 UI 過濾、非 schema 裁剪：舊 DocumentPdfConvertPanel.vue 依
 * currentFileExt 動態排除非 PDF 檔的 'images' 選項；schema 在此維持後端全集三選項
 * （registry outputKind 的 images→image 判斷函式沿用同一份靜態全集，見 registry.ts 該筆
 * 條目註解——手寫不動）。動態過濾邏輯搬進 PdfConvertParams.vue（見該檔 isPdf/
 * currentFileExt prop）。
 *
 * ⚠ agent 欄位擴大決策：ToolParamHost 的 agentFields 合成只吃 meta.schema 的靜態
 * options（單一 truth source），visibleWhen 只吃 params、不吃 fileInfo/掛載點才知道的
 * 副檔名——因此 agent 面板固定看到三個選項（含 images），比舊
 * DocumentPdfConvertPanel.agentSchema（依 isPdf 動態產生）稍寬。若 agent 對非 PDF 檔選
 * 'images'，後端依副檔名 raise ValueError（422 execution failed，非靜默錯誤）。此取捨沿
 * batch4-recon.md §9 pdf_convert 節記載的既定決策，非本檔獨創。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'document.pdf_convert',
  apiPath: '/document/pdf-convert',
  labelKey: 'document.pdf_convert.task_label',
  taskType: 'document.pdf_convert',
  schema: [
    { name: 'output_format', type: 'enum', options: ['txt', 'md', 'images'], default: 'txt' },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // 舊 View.handleMultiExecute 的 'pdf-convert' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 DocumentPdfConvertPanel.agentSchema.execute：{requiresConfirm:false,label:'panel.doc_pdf_convert.execute'}。
  agentRequiresConfirm: false,
  agentExecuteLabel: 'panel.doc_pdf_convert.execute',
  // 無 seedOnFileChange（無需 fileInfo 衍生初值）、無 modelRequirement（不需模型）——刻意省略。
}

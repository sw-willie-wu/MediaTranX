import { inject } from 'vue'
import type { AgentCompositeField } from '@/components/params/types'

export type RegisterCompositeFn = (c: AgentCompositeField) => () => void

/**
 * `inject('registerComposite')`（由 ToolParamHost.vue 提供）的共用包裝——收斂統一參數元件
 * 案 8 個消費者（LyricsParams/TranscribeParams/UpscaleParams/InterpolateParams/OcrParams/
 * SummaryParams/TranslateParams/EnhanceParams——SubtitleParams 的 composite 已於 W1-4
 * 刪除故不在列）重複的 inject 呼叫，並帶
 * `null` 預設值消除 pipeline/殼語境（PipelineParamForm 未 provide 此 key）下 Vue 的
 * `injection "registerComposite" not found` 開發期警告——語意不變：呼叫端一律用
 * `registerComposite?.(...)` 選擇性呼叫，未提供時安靜跳過。
 */
export function useRegisterComposite(): RegisterCompositeFn | null {
  return inject<RegisterCompositeFn | null>('registerComposite', null)
}

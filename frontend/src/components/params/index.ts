/**
 * 參數元件載入表（統一參數元件 spec §3）——兩側 host（ToolParamHost/PipelineParamForm）共用。
 * PARAM_COMPONENTS 懶載（defineAsyncComponent），METAS 同步（純資料，不拖 SFC 進模組圖）。
 */
import { defineAsyncComponent, type Component } from 'vue'
import type { ToolParamMeta } from './types'
import { META as CUT_META } from './video/cut.meta'
import { META as TRANSCODE_META } from './video/transcode.meta'
import { META as EXTRACT_AUDIO_META } from './video/extract_audio.meta'
import { META as TRANSLATE_META } from './document/translate.meta'

export const PARAM_COMPONENTS: Record<string, Component> = {
  'video.cut': defineAsyncComponent(() => import('./video/CutParams.vue')),
  'video.transcode': defineAsyncComponent(() => import('./video/TranscodeParams.vue')),
  'video.extract_audio': defineAsyncComponent(() => import('./video/ExtractAudioParams.vue')),
  'document.translate': defineAsyncComponent(() => import('./document/TranslateParams.vue')),
}

export const METAS: Record<string, ToolParamMeta> = {
  'video.cut': CUT_META,
  'video.transcode': TRANSCODE_META,
  'video.extract_audio': EXTRACT_AUDIO_META,
  'document.translate': TRANSLATE_META,
}

export function hasParamComponent(toolKey: string): boolean {
  return toolKey in PARAM_COMPONENTS
}

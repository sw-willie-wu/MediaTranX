/**
 * 參數元件載入表（統一參數元件 spec §3）——兩側 host（ToolParamHost/PipelineParamForm）共用。
 * PARAM_COMPONENTS 懶載（defineAsyncComponent），METAS 同步（純資料，不拖 SFC 進模組圖）。
 */
import { defineAsyncComponent, type Component } from 'vue'
import type { ToolParamMeta } from './types'
import { META as CUT_META } from './video/cut.meta'
import { META as CROP_META } from './video/crop.meta'
import { META as TRANSCODE_META } from './video/transcode.meta'
import { META as EXTRACT_AUDIO_META } from './video/extract_audio.meta'
import { META as DOWNLOAD_META } from './video/download.meta'
import { META as INTERPOLATE_META } from './video/interpolate.meta'
import { META as ENHANCE_META } from './video/enhance.meta'
import { META as SUMMARY_META } from './video/summary.meta'
import { META as SUBTITLE_META } from './video/subtitle.meta'
import { META as TRANSLATE_META } from './document/translate.meta'
import { META as AUDIO_TRANSCODE_META } from './audio/transcode.meta'
import { META as AUDIO_VOLUME_META } from './audio/volume.meta'
import { META as AUDIO_CUT_META } from './audio/cut.meta'
import { META as AUDIO_SEPARATE_META } from './audio/separate.meta'
import { META as AUDIO_TRANSCRIBE_META } from './audio/transcribe.meta'
import { META as AUDIO_LYRICS_META } from './audio/lyrics.meta'

export const PARAM_COMPONENTS: Record<string, Component> = {
  'video.cut': defineAsyncComponent(() => import('./video/CutParams.vue')),
  'video.crop': defineAsyncComponent(() => import('./video/CropParams.vue')),
  'video.transcode': defineAsyncComponent(() => import('./video/TranscodeParams.vue')),
  'video.extract_audio': defineAsyncComponent(() => import('./video/ExtractAudioParams.vue')),
  'video.download': defineAsyncComponent(() => import('./video/DownloadParams.vue')),
  'video.interpolate': defineAsyncComponent(() => import('./video/InterpolateParams.vue')),
  'video.enhance': defineAsyncComponent(() => import('./video/EnhanceParams.vue')),
  'video.summary': defineAsyncComponent(() => import('./video/SummaryParams.vue')),
  // 例外殼工具（批 2 Task 2.5）：video.subtitle 的組件是 SubtitleParams.vue（表單本體，非
  // 整個殼）——pipeline dispatcher 掛這個；工具頁走 SubtitlePanel.vue 自建 template 直接掛載
  // （不經 ToolParamHost，見 SubtitlePanel.vue 檔頭註解），本表僅供 pipeline 側使用。
  'video.subtitle': defineAsyncComponent(() => import('./video/SubtitleParams.vue')),
  'document.translate': defineAsyncComponent(() => import('./document/TranslateParams.vue')),
  'audio.transcode': defineAsyncComponent(() => import('./audio/AudioTranscodeParams.vue')),
  'audio.volume': defineAsyncComponent(() => import('./audio/VolumeParams.vue')),
  'audio.cut': defineAsyncComponent(() => import('./audio/AudioCutParams.vue')),
  'audio.separate': defineAsyncComponent(() => import('./audio/SeparateParams.vue')),
  'audio.transcribe': defineAsyncComponent(() => import('./audio/TranscribeParams.vue')),
  'audio.lyrics': defineAsyncComponent(() => import('./audio/LyricsParams.vue')),
}

export const METAS: Record<string, ToolParamMeta> = {
  'video.cut': CUT_META,
  'video.crop': CROP_META,
  'video.transcode': TRANSCODE_META,
  'video.extract_audio': EXTRACT_AUDIO_META,
  'video.download': DOWNLOAD_META,
  'video.interpolate': INTERPOLATE_META,
  'video.enhance': ENHANCE_META,
  'video.summary': SUMMARY_META,
  'video.subtitle': SUBTITLE_META,
  'document.translate': TRANSLATE_META,
  'audio.transcode': AUDIO_TRANSCODE_META,
  'audio.volume': AUDIO_VOLUME_META,
  'audio.cut': AUDIO_CUT_META,
  'audio.separate': AUDIO_SEPARATE_META,
  'audio.transcribe': AUDIO_TRANSCRIBE_META,
  'audio.lyrics': AUDIO_LYRICS_META,
}

export function hasParamComponent(toolKey: string): boolean {
  return toolKey in PARAM_COMPONENTS
}

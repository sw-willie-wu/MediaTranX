/**
 * Tool registry — pipeline 節點白名單（25 工具 + 1 source）。
 * param_schema 以後端各 route 的 Pydantic request model 為準（欄位/預設值照抄;
 * file_id / suppress_results 不進 schema）。互動工具（ai-remove 畫遮罩／
 * subtitle 編輯燒錄流）與 multipart 的 audio.midi 不在白名單;cut/crop（影音圖）
 * 與字幕「提取」以面板數值入列（2026-07-07 User 決策,推翻 v1 傘型排除）。
 *
 * 建模限制（現況）:dict / list 型欄位（translate 的 glossary 等）批 0 已解禁,
 * ParamField 六型別含 dict/list,已入 paramSchema（見 document.translate 的
 * glossary）;runner 對 node.params 原樣透傳,後端 default（stems=None=全部、
 * glossary=None）補位。唯一例外是 ToolParamHost 的 agent 兩層合成——dict/list
 * 欄位不曝給 agent 的 set_field 介面（scalar 無法表達 dict,字串硬塞會 422）,
 * 但仍留在 paramSchema／pipeline 節點表單裡,只是 agent 面板看不到、要用
 * create_pipeline 走 dict 全量帶入（見 components/params/ToolParamHost.vue
 * agentFields）。動態模型系欄位（model_id/provider/conn_id/remote_model/
 * 語言清單）標 advanced 且不給 options。
 */
import type { MediaKindT, ParamField, ToolSpec } from './types'
import { META as CUT_META } from '@/components/params/video/cut.meta'
import { META as CROP_META } from '@/components/params/video/crop.meta'
import { META as TRANSCODE_META, AUDIO_FORMATS as TRANSCODE_AUDIO_FORMATS } from '@/components/params/video/transcode.meta'
import { META as EXTRACT_AUDIO_META } from '@/components/params/video/extract_audio.meta'
import { META as DOWNLOAD_META } from '@/components/params/video/download.meta'
import { META as INTERPOLATE_META } from '@/components/params/video/interpolate.meta'
import { META as ENHANCE_META } from '@/components/params/video/enhance.meta'
import { META as SUMMARY_META } from '@/components/params/video/summary.meta'
import { META as SUBTITLE_META } from '@/components/params/video/subtitle.meta'
import { META as TRANSLATE_META } from '@/components/params/document/translate.meta'
import { META as AUDIO_TRANSCODE_META } from '@/components/params/audio/transcode.meta'
import { META as AUDIO_VOLUME_META } from '@/components/params/audio/volume.meta'
import { META as AUDIO_CUT_META } from '@/components/params/audio/cut.meta'
import { META as AUDIO_SEPARATE_META } from '@/components/params/audio/separate.meta'
import { META as AUDIO_TRANSCRIBE_META } from '@/components/params/audio/transcribe.meta'
import { META as AUDIO_LYRICS_META } from '@/components/params/audio/lyrics.meta'
import { META as IMAGE_COMPRESS_META } from '@/components/params/image/compress.meta'
import { META as IMAGE_CONVERT_META } from '@/components/params/image/convert.meta'

const AUDIO_OUT = (): MediaKindT => 'audio'
const VIDEO_OUT = (): MediaKindT => 'video'
const IMAGE_OUT = (): MediaKindT => 'image'
const DOCUMENT_OUT = (): MediaKindT => 'document'

const VIDEO_IMAGE_FORMATS = new Set(['gif', 'apng'])

/** image.ocr / document.ocr 共用的 VLM 模型欄位（本地 family/size 或 remote 三元組） */
function vlmModelFields(): ParamField[] {
  return [
    { name: 'model_family', type: 'string', advanced: true },
    { name: 'model_size', type: 'string', default: '4b', advanced: true },
    { name: 'quantization', type: 'string', advanced: true },
    { name: 'remote', type: 'boolean', default: false, advanced: true },
    { name: 'provider', type: 'string', advanced: true },
    { name: 'conn_id', type: 'number', advanced: true },
    { name: 'remote_model', type: 'string', advanced: true },
  ]
}

export const TOOL_REGISTRY: Record<string, ToolSpec> = {
  // ── source ────────────────────────────────────────────────────────
  // paramSchema 由 META 組裝（統一參數元件案，批 2 Task 2.2）:欄位定義唯一事實來源在
  // download.meta.ts。舊版此處把 format_intent 誤建成 scalar enum，與後端巢狀
  // FormatIntent 物件不符（422 風險）——已修正為 dict 型別，見 download.meta.ts 檔頭註記。
  'video.download': {
    toolKey: DOWNLOAD_META.toolKey,
    apiPath: DOWNLOAD_META.apiPath,
    labelKey: DOWNLOAD_META.labelKey,
    kind: 'source',
    inputKinds: [],
    outputKind: VIDEO_OUT,
    paramSchema: DOWNLOAD_META.schema,
  },

  // ── video ─────────────────────────────────────────────────────────
  // paramSchema 由 META 組裝（統一參數元件案）:欄位定義唯一事實來源在 transcode.meta.ts /
  // extract_audio.meta.ts;outputKind 是參數的函數,手寫保留在 registry。
  'video.transcode': {
    toolKey: TRANSCODE_META.toolKey,
    apiPath: TRANSCODE_META.apiPath,
    labelKey: TRANSCODE_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    // schema 的 output_format 是「視訊＋動圖＋音訊」超集（工具頁由 buildSubmit 分流,
    // pipeline 節點沒有這層分流——見 transcode.meta.ts 檔頭註記）;outputKind 對超集要 robust。
    outputKind: (p) => {
      const fmt = String(p.output_format ?? 'mp4')
      if (VIDEO_IMAGE_FORMATS.has(fmt)) return 'image'
      if (TRANSCODE_AUDIO_FORMATS.has(fmt)) return 'audio'
      return 'video'
    },
    paramSchema: TRANSCODE_META.schema,
  },

  'video.extract_audio': {
    toolKey: EXTRACT_AUDIO_META.toolKey,
    apiPath: EXTRACT_AUDIO_META.apiPath,
    labelKey: EXTRACT_AUDIO_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: AUDIO_OUT,
    paramSchema: EXTRACT_AUDIO_META.schema,
  },

  'video.cut': {
    toolKey: CUT_META.toolKey,
    apiPath: CUT_META.apiPath,
    labelKey: CUT_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    // paramSchema 由 META 組裝（統一參數元件案）:欄位定義唯一事實來源在 cut.meta.ts
    paramSchema: CUT_META.schema,
  },

  'video.crop': {
    toolKey: CROP_META.toolKey,
    apiPath: CROP_META.apiPath,
    labelKey: CROP_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    // paramSchema 由 META 組裝（統一參數元件案,批 2 Task 2.1）:欄位定義唯一事實來源在
    // crop.meta.ts（含 width/height min=2 的 UI 收斂約束 — 後端向下取偶(yuv420p),
    // 1 會取到 0 直接 ValueError,故 min 2;奇數 ≥3 合法(161→160)）
    paramSchema: CROP_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 2 Task 2.5——例外殼工具）:欄位定義唯一事實
  // 來源在 subtitle.meta.ts（含 glossary(dict)——v1 排除已於本 task 解禁加回,20 欄全集）。
  // 註:toolKey 'video.subtitle' ≠ 後端 task_type 'video.subtitle_generate' ≠ 前端
  // taskStore.addTask 手寫 taskType 'subtitle/generate' — 全 registry 唯一三名不同者;
  // 無害(label 各路徑同字樣),別誤當 bug（見 subtitle.meta.ts META.taskType 註解）。
  'video.subtitle': {
    toolKey: SUBTITLE_META.toolKey,
    apiPath: SUBTITLE_META.apiPath,
    labelKey: SUBTITLE_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: DOCUMENT_OUT,
    paramSchema: SUBTITLE_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 2 Task 2.3）:欄位定義唯一事實來源在
  // enhance.meta.ts。
  'video.enhance': {
    toolKey: ENHANCE_META.toolKey,
    apiPath: ENHANCE_META.apiPath,
    labelKey: ENHANCE_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    paramSchema: ENHANCE_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 2 Task 2.3）:欄位定義唯一事實來源在
  // interpolate.meta.ts（含後端 InterpolateRequest default 'v4.22' 過時的收斂註記）。
  'video.interpolate': {
    toolKey: INTERPOLATE_META.toolKey,
    apiPath: INTERPOLATE_META.apiPath,
    labelKey: INTERPOLATE_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    paramSchema: INTERPOLATE_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 2 Task 2.4）:欄位定義唯一事實來源在
  // summary.meta.ts（含 min_silence_duration_ms/vad_threshold UI range 收斂為 100-2000/50
  // 與 0.1-0.9/0.05 的設計定案註記——與此處舊字面值不同,以 META 為準）。
  'video.summary': {
    toolKey: SUMMARY_META.toolKey,
    apiPath: SUMMARY_META.apiPath,
    labelKey: SUMMARY_META.labelKey,
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: DOCUMENT_OUT,
    paramSchema: SUMMARY_META.schema,
  },

  // ── audio ─────────────────────────────────────────────────────────
  // paramSchema 由 META 組裝（統一參數元件案，批 3 Task 3.1）：欄位定義唯一事實來源在
  // transcode.meta.ts（含 wma 全集，LOSSLESS_FORMATS 常量搬進該檔——與此處舊
  // LOSSLESS_AUDIO_FORMATS 同義，見 audio_bitrate 舊寫死片段已移除）。
  'audio.transcode': {
    toolKey: AUDIO_TRANSCODE_META.toolKey,
    apiPath: AUDIO_TRANSCODE_META.apiPath,
    labelKey: AUDIO_TRANSCODE_META.labelKey,
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    paramSchema: AUDIO_TRANSCODE_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 3 Task 3.5——批 3 收官）：欄位定義唯一事實
  // 來源在 audio/lyrics.meta.ts（15 欄全集；無 vocal_separation/summarize，demucs 需求無條件，
  // 見該檔檔頭「與 audio.transcribe 的關鍵差異」）。
  'audio.lyrics': {
    toolKey: AUDIO_LYRICS_META.toolKey,
    apiPath: AUDIO_LYRICS_META.apiPath,
    labelKey: AUDIO_LYRICS_META.labelKey,
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: DOCUMENT_OUT,
    paramSchema: AUDIO_LYRICS_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 3 Task 3.3）：欄位定義唯一事實來源在
  // audio/separate.meta.ts。stems（List[str]，None=全部）已入 schema（type:'list'），但
  // 不進 agent set_field 介面（見 ToolParamHost.vue agentFields 濾除 list/dict）。
  'audio.separate': {
    toolKey: AUDIO_SEPARATE_META.toolKey,
    apiPath: AUDIO_SEPARATE_META.apiPath,
    labelKey: AUDIO_SEPARATE_META.labelKey,
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    paramSchema: AUDIO_SEPARATE_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 3 Task 3.4）：欄位定義唯一事實來源在
  // audio/transcribe.meta.ts（29 欄全集，含 summarize 第三組動態模型系——subtitle/summary
  // 皆無；翻譯 gate 是獨立 translate bool，非 subtitle 的 target_language 非空判準）。
  'audio.transcribe': {
    toolKey: AUDIO_TRANSCRIBE_META.toolKey,
    apiPath: AUDIO_TRANSCRIBE_META.apiPath,
    labelKey: AUDIO_TRANSCRIBE_META.labelKey,
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: DOCUMENT_OUT,
    paramSchema: AUDIO_TRANSCRIBE_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 3 Task 3.1）：欄位定義唯一事實來源在
  // volume.meta.ts。
  'audio.volume': {
    toolKey: AUDIO_VOLUME_META.toolKey,
    apiPath: AUDIO_VOLUME_META.apiPath,
    labelKey: AUDIO_VOLUME_META.labelKey,
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    paramSchema: AUDIO_VOLUME_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 3 Task 3.2）：欄位定義唯一事實來源在
  // audio/cut.meta.ts。後端合約是 HH:MM:SS 字串(AudioCutRequest)，與 video.cut 的秒數
  // float 不同 — string 欄位。
  'audio.cut': {
    toolKey: AUDIO_CUT_META.toolKey,
    apiPath: AUDIO_CUT_META.apiPath,
    labelKey: AUDIO_CUT_META.labelKey,
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    paramSchema: AUDIO_CUT_META.schema,
  },

  // ── image ─────────────────────────────────────────────────────────
  // paramSchema 由 META 組裝（統一參數元件案，批 4 Task 4.1）：欄位定義唯一事實來源在
  // compress.meta.ts（含 strength default 60→75 的刻意偏離決策，見該檔檔頭註記——pipeline
  // 節點初值隨之改變，非疏漏）。
  'image.compress': {
    toolKey: IMAGE_COMPRESS_META.toolKey,
    apiPath: IMAGE_COMPRESS_META.apiPath,
    labelKey: IMAGE_COMPRESS_META.labelKey,
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: IMAGE_COMPRESS_META.schema,
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 4 Task 4.1）：欄位定義唯一事實來源在
  // convert.meta.ts（含 width/height/scale 三態互斥的 buildSubmit 清理，見該檔檔頭註記）。
  'image.convert': {
    toolKey: IMAGE_CONVERT_META.toolKey,
    apiPath: IMAGE_CONVERT_META.apiPath,
    labelKey: IMAGE_CONVERT_META.labelKey,
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: IMAGE_CONVERT_META.schema,
  },

  'image.filter': {
    toolKey: 'image.filter',
    apiPath: '/image/filter',
    labelKey: 'image.filter.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: [
      { name: 'brightness', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
      { name: 'contrast', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
      { name: 'saturation', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
      { name: 'hue', type: 'number', min: -180, max: 180, step: 1, default: 0 },
      { name: 'sharpness', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
      { name: 'warmth', type: 'number', min: -1, max: 1, step: 0.05, default: 0 },
      { name: 'grayscale', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
      { name: 'sepia', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
      { name: 'invert', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
      { name: 'blur', type: 'number', min: 0, max: 100, step: 0.5, default: 0 },
      { name: 'vignette', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
    ],
  },

  'image.ocr': {
    toolKey: 'image.ocr',
    apiPath: '/image/ocr',
    labelKey: 'image.ocr.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: DOCUMENT_OUT,
    paramSchema: [
      { name: 'output_format', type: 'enum', options: ['md', 'txt'], default: 'md' },
      ...vlmModelFields(),
    ],
  },

  'image.remove_bg': {
    toolKey: 'image.remove_bg',
    apiPath: '/image/remove-bg',
    labelKey: 'image.remove_bg.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: [
      { name: 'mode', type: 'enum', options: ['auto', 'person', 'product', 'animal', 'anime'], default: 'auto' },
    ],
  },

  'image.upscale': {
    toolKey: 'image.upscale',
    apiPath: '/image/upscale',
    labelKey: 'image.upscale.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: [
      // model_id 跨 family（realesrgan/swinir/waifu2x…）動態模型系,不列 options
      { name: 'model_id', type: 'string', default: 'realesrgan-x4plus', advanced: true },
      { name: 'scale', type: 'number', min: 2, max: 4, step: 1, default: 4 },
      { name: 'sharpen', type: 'boolean', default: false },
      { name: 'face_fix', type: 'boolean', default: false },
      { name: 'face_restore_model_id', type: 'string', advanced: true, visibleWhen: (p) => p.face_fix === true },
      { name: 'face_restore_upscale', type: 'number', min: 1, max: 4, step: 1, default: 2, advanced: true, visibleWhen: (p) => p.face_fix === true },
    ],
  },

  'image.crop': {
    toolKey: 'image.crop',
    apiPath: '/image/crop',
    labelKey: 'image.crop.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    // PIL 裁切無取偶限制(ImageCropRequest) — min 1 即可
    paramSchema: [
      { name: 'x', type: 'number', min: 0, step: 1, default: 0 },
      { name: 'y', type: 'number', min: 0, step: 1, default: 0 },
      { name: 'width', type: 'number', min: 1, step: 1 },
      { name: 'height', type: 'number', min: 1, step: 1 },
    ],
  },

  // ── document ──────────────────────────────────────────────────────
  'document.ocr': {
    toolKey: 'document.ocr',
    apiPath: '/document/ocr',
    labelKey: 'document.ocr.task_label',
    kind: 'tool',
    inputKinds: ['document'],
    outputKind: DOCUMENT_OUT,
    paramSchema: [
      { name: 'output_format', type: 'enum', options: ['md', 'txt'], default: 'md' },
      ...vlmModelFields(),
    ],
  },

  'document.pdf_convert': {
    toolKey: 'document.pdf_convert',
    apiPath: '/document/pdf-convert',
    labelKey: 'document.pdf_convert.task_label',
    kind: 'tool',
    // 後端吃 pdf/docx/doc/txt;僅 'images' 限 pdf（後端 ValueError 把關）
    inputKinds: ['document'],
    // 'images' 實際產出是 zip（多頁打包）——歸 image 類供下游判斷,
    // 但 zip 不在 MEDIA_KIND_EXTS,下游 image 工具實際吃不動（v1 已知限制）
    outputKind: (p) => (p.output_format === 'images' ? 'image' : 'document'),
    paramSchema: [
      { name: 'output_format', type: 'enum', options: ['txt', 'md', 'images'], default: 'txt' },
    ],
  },

  'document.split': {
    toolKey: 'document.split',
    apiPath: '/document/split',
    labelKey: 'document.split.task_label',
    kind: 'tool',
    inputKinds: ['document'],
    inputExts: ['pdf'],   // 後端 pypdf 直讀,僅支援 PDF
    outputKind: DOCUMENT_OUT,
    paramSchema: [
      { name: 'pages', type: 'string', default: '' },
    ],
  },

  // paramSchema 由 META 組裝（統一參數元件案，批 1 Task 1.5）：欄位定義唯一事實來源在
  // translate.meta.ts（含 glossary dict——批 0 已解禁 dict 型別，不再排除）。
  'document.translate': {
    toolKey: TRANSLATE_META.toolKey,
    apiPath: TRANSLATE_META.apiPath,
    labelKey: TRANSLATE_META.labelKey,
    kind: 'tool',
    inputKinds: ['document'],
    outputKind: DOCUMENT_OUT,
    paramSchema: TRANSLATE_META.schema,
  },
}

export function getToolSpec(toolKey: string): ToolSpec | undefined {
  return TOOL_REGISTRY[toolKey]
}

export function listToolSpecs(): ToolSpec[] {
  return Object.values(TOOL_REGISTRY)
}

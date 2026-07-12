/**
 * Tool registry — pipeline 節點白名單（25 工具 + 1 source）。
 * param_schema 以後端各 route 的 Pydantic request model 為準（欄位/預設值照抄;
 * file_id / suppress_results 不進 schema）。互動工具（ai-remove 畫遮罩／
 * subtitle 編輯燒錄流）與 multipart 的 audio.midi 不在白名單;cut/crop（影音圖）
 * 與字幕「提取」以面板數值入列（2026-07-07 User 決策,推翻 v1 傘型排除）。
 *
 * 建模限制（v1）:dict / list 型欄位（translate/lyrics 的 glossary、
 * separate 的 stems）不進 paramSchema——ParamField 四型別無法表達,列了反而
 * 讓合法值被 param_invalid 打死;runner 對 node.params 原樣透傳,後端 default
 * （stems=None=全部、glossary=None）補位。動態模型系欄位（model_id/
 * provider/conn_id/remote_model/語言清單）標 advanced 且不給 options。
 */
import type { MediaKindT, ParamField, ToolSpec } from './types'
import { META as CUT_META } from '@/components/params/video/cut.meta'
import { META as TRANSCODE_META, AUDIO_FORMATS as TRANSCODE_AUDIO_FORMATS } from '@/components/params/video/transcode.meta'
import { META as EXTRACT_AUDIO_META } from '@/components/params/video/extract_audio.meta'

const AUDIO_OUT = (): MediaKindT => 'audio'
const VIDEO_OUT = (): MediaKindT => 'video'
const IMAGE_OUT = (): MediaKindT => 'image'
const DOCUMENT_OUT = (): MediaKindT => 'document'

const VIDEO_IMAGE_FORMATS = new Set(['gif', 'apng'])

// 後端 adapters/ai/registry.py whisper variants（stt 靜態清單）
const WHISPER_SIZES = ['tiny', 'base', 'small', 'medium', 'large-v3']
// 後端 translate 風格常數（document/translate.py 描述: colloquial, formal, literal）
const TRANSLATE_STYLES = ['colloquial', 'formal', 'literal']
// audio/transcode.py _FORMAT_CODEC_MAP 無損格式（不需 bitrate）
const LOSSLESS_AUDIO_FORMATS = new Set(['flac', 'wav', 'alac', 'aiff'])

/** transcribe/lyrics 共用的翻譯子欄位（translate=true 才顯示;glossary 見檔頭註記） */
function translateSubFields(visible: (p: Record<string, unknown>) => boolean): ParamField[] {
  return [
    { name: 'target_language', type: 'string', advanced: true, visibleWhen: visible },
    { name: 'translate_model_family', type: 'string', default: 'gemma4', advanced: true, visibleWhen: visible },
    { name: 'translate_model_size', type: 'string', default: '4b', advanced: true, visibleWhen: visible },
    { name: 'translate_quantization', type: 'string', advanced: true, visibleWhen: visible },
    { name: 'translate_remote', type: 'boolean', default: false, advanced: true, visibleWhen: visible },
    { name: 'translate_provider', type: 'string', advanced: true, visibleWhen: visible },
    { name: 'translate_conn_id', type: 'number', advanced: true, visibleWhen: visible },
    { name: 'translate_remote_model', type: 'string', advanced: true, visibleWhen: visible },
    { name: 'keep_names', type: 'boolean', default: true, advanced: true, visibleWhen: visible },
    { name: 'translate_style', type: 'enum', options: TRANSLATE_STYLES, default: 'colloquial', advanced: true, visibleWhen: visible },
  ]
}

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
  'video.download': {
    toolKey: 'video.download',
    apiPath: '/video/download',
    labelKey: 'video.download.task_label',
    kind: 'source',
    inputKinds: [],
    outputKind: VIDEO_OUT,
    paramSchema: [
      { name: 'url', type: 'string' },
      { name: 'format_intent', type: 'enum', options: ['auto', 'video', 'audio'], default: 'auto', advanced: true },
    ],
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
    toolKey: 'video.crop',
    apiPath: '/video/crop',
    labelKey: 'video.crop.task_label',
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    // width/height 必填;後端向下取偶(yuv420p) — 1 會取到 0 直接 ValueError,
    // 故 min 2;奇數 ≥3 合法(161→160)
    paramSchema: [
      { name: 'x', type: 'number', min: 0, step: 1, default: 0 },
      { name: 'y', type: 'number', min: 0, step: 1, default: 0 },
      { name: 'width', type: 'number', min: 2, step: 1 },
      { name: 'height', type: 'number', min: 2, step: 1 },
    ],
  },

  'video.subtitle': {
    toolKey: 'video.subtitle',
    apiPath: '/video/subtitle/generate',
    labelKey: 'video.subtitle.task_label',
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: DOCUMENT_OUT,
    // SubtitleGenerateRequest(subtitle.py)欄位照抄;glossary 為 dict — v1 建模
    // 限制排除(檔頭規則)。翻譯子欄位 gate 是 target_language 非空(string、非
    // boolean),v1 全標 advanced 不做 visibleWhen。
    // 註:toolKey 'video.subtitle' ≠ 後端 task_type 'video.subtitle_generate' —
    // 全 registry 唯一不同名;無害(label 兩路徑同字樣),別誤當 bug。
    paramSchema: [
      { name: 'source_language', type: 'string', advanced: true },
      { name: 'model_size', type: 'enum', options: WHISPER_SIZES, default: 'medium' },
      { name: 'output_format', type: 'enum', options: ['srt', 'vtt'], default: 'srt' },
      { name: 'target_language', type: 'string', advanced: true },
      { name: 'translate_model_family', type: 'string', default: 'gemma4', advanced: true },
      { name: 'translate_model_size', type: 'string', default: '4b', advanced: true },
      { name: 'translate_quantization', type: 'string', advanced: true },
      { name: 'translate_remote', type: 'boolean', default: false, advanced: true },
      { name: 'translate_provider', type: 'string', advanced: true },
      { name: 'translate_conn_id', type: 'number', advanced: true },
      { name: 'translate_remote_model', type: 'string', advanced: true },
      { name: 'keep_names', type: 'boolean', default: true, advanced: true },
      { name: 'translate_style', type: 'enum', options: TRANSLATE_STYLES, default: 'colloquial', advanced: true },
      { name: 'word_timestamps', type: 'boolean', default: false, advanced: true },
      { name: 'condition_on_previous_text', type: 'boolean', default: true, advanced: true },
      { name: 'min_silence_duration_ms', type: 'number', min: 100, max: 2000, step: 50, default: 200, advanced: true },
      { name: 'vad_threshold', type: 'number', min: 0.1, max: 0.9, step: 0.05, default: 0.3, advanced: true },
      { name: 'align', type: 'boolean', default: false, advanced: true },
      { name: 'vocal_separation', type: 'boolean', default: false, advanced: true },
    ],
  },

  'video.enhance': {
    toolKey: 'video.enhance',
    apiPath: '/video/enhance',
    labelKey: 'video.enhance.task_label',
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    paramSchema: [
      { name: 'model', type: 'string', default: 'realesrgan', advanced: true },
      { name: 'variant', type: 'enum', options: ['x2plus', 'x4plus', 'x4plus-anime', 'animevideov3'], default: 'x4plus' },
      { name: 'output_format', type: 'enum', options: ['mp4', 'mkv', 'webm', 'mov'], default: 'mp4' },
      { name: 'video_codec', type: 'enum', options: ['h264', 'h265', 'vp9', 'av1'], default: 'h264' },
    ],
  },

  'video.interpolate': {
    toolKey: 'video.interpolate',
    apiPath: '/video/interpolate',
    labelKey: 'video.interpolate.task_label',
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: VIDEO_OUT,
    // 後端 InterpolateRequest default 'v4.22' 已過時（registry 只有 v4.26,
    // panel default 也是 v4.26）——這裡壓 v4.26 避免 default 即失敗。
    paramSchema: [
      { name: 'model', type: 'enum', options: ['v4.26'], default: 'v4.26', advanced: true },
      { name: 'mode', type: 'enum', options: ['2x', '4x', 'custom'], default: '2x' },
      { name: 'target_fps', type: 'number', min: 2, max: 240, step: 1, visibleWhen: (p) => p.mode === 'custom' },
      { name: 'output_format', type: 'enum', options: ['mp4', 'mkv', 'webm', 'mov'], default: 'mp4' },
      { name: 'video_codec', type: 'enum', options: ['h264', 'h265', 'vp9', 'av1'], default: 'h264' },
    ],
  },

  'video.summary': {
    toolKey: 'video.summary',
    apiPath: '/video/summary',
    labelKey: 'video.summary.task_label',
    kind: 'tool',
    inputKinds: ['video'],
    outputKind: DOCUMENT_OUT,
    paramSchema: [
      { name: 'summary_mode', type: 'enum', options: ['bullets', 'narrative'], default: 'bullets' },
      { name: 'language', type: 'string', default: 'zh-TW' },
      { name: 'whisper_model_size', type: 'enum', options: WHISPER_SIZES, default: 'medium' },
      // LLM — 本地（family+size）或 remote 三元組,動態模型系
      { name: 'llm_model_family', type: 'string', advanced: true },
      { name: 'llm_model_size', type: 'string', advanced: true },
      { name: 'llm_remote', type: 'boolean', default: false, advanced: true },
      { name: 'llm_provider', type: 'string', advanced: true },
      { name: 'llm_conn_id', type: 'number', advanced: true },
      { name: 'llm_remote_model', type: 'string', advanced: true },
      // VLM — 選配
      { name: 'vlm_model_family', type: 'string', advanced: true },
      { name: 'vlm_model_size', type: 'string', advanced: true },
      { name: 'vlm_remote', type: 'boolean', default: false, advanced: true },
      { name: 'vlm_provider', type: 'string', advanced: true },
      { name: 'vlm_conn_id', type: 'number', advanced: true },
      { name: 'vlm_remote_model', type: 'string', advanced: true },
      // Whisper 進階
      { name: 'vocal_separation', type: 'boolean', default: false, advanced: true },
      { name: 'align', type: 'boolean', default: false, advanced: true },
      { name: 'word_timestamps', type: 'boolean', default: false, advanced: true },
      { name: 'condition_on_previous_text', type: 'boolean', default: true, advanced: true },
      { name: 'min_silence_duration_ms', type: 'number', min: 0, step: 50, default: 200, advanced: true },
      { name: 'vad_threshold', type: 'number', min: 0, max: 1, step: 0.05, default: 0.3, advanced: true },
    ],
  },

  // ── audio ─────────────────────────────────────────────────────────
  'audio.transcode': {
    toolKey: 'audio.transcode',
    apiPath: '/audio/transcode',
    labelKey: 'audio.transcode.task_label',
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    paramSchema: [
      // options = 後端 _FORMAT_CODEC_MAP 全集
      { name: 'output_format', type: 'enum', options: ['mp3', 'aac', 'm4a', 'ogg', 'opus', 'wma', 'flac', 'wav', 'alac', 'aiff'], default: 'mp3' },
      { name: 'audio_bitrate', type: 'enum', options: ['128k', '192k', '256k', '320k'], default: '192k', advanced: true, visibleWhen: (p) => !LOSSLESS_AUDIO_FORMATS.has(String(p.output_format)) },
      { name: 'sample_rate', type: 'number', min: 8000, max: 192000, step: 100, advanced: true },
      { name: 'channels', type: 'number', min: 1, max: 2, step: 1, advanced: true },
    ],
  },

  'audio.lyrics': {
    toolKey: 'audio.lyrics',
    apiPath: '/audio/lyrics',
    labelKey: 'audio.lyrics.task_label',
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: DOCUMENT_OUT,
    paramSchema: [
      { name: 'model_size', type: 'enum', options: WHISPER_SIZES, default: 'medium' },
      { name: 'output_format', type: 'enum', options: ['lrc', 'txt'], default: 'lrc' },
      { name: 'align', type: 'boolean', default: false },
      { name: 'translate', type: 'boolean', default: false },
      ...translateSubFields((p) => p.translate === true),
    ],
  },

  'audio.separate': {
    toolKey: 'audio.separate',
    apiPath: '/audio/separate',
    labelKey: 'audio.separate.task_label',
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    // stems（List[str]、None=全部）v1 不建模——見檔頭註記
    paramSchema: [
      { name: 'model_name', type: 'enum', options: ['htdemucs_6s'], default: 'htdemucs_6s', advanced: true },
      { name: 'output_format', type: 'enum', options: ['wav', 'flac', 'mp3'], default: 'wav' },
      { name: 'generate_midi', type: 'boolean', default: false },
    ],
  },

  'audio.transcribe': {
    toolKey: 'audio.transcribe',
    apiPath: '/audio/transcribe',
    labelKey: 'audio.transcribe.task_label',
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: DOCUMENT_OUT,
    paramSchema: [
      { name: 'model_size', type: 'enum', options: WHISPER_SIZES, default: 'medium' },
      { name: 'output_format', type: 'enum', options: ['txt', 'srt'], default: 'txt' },
      // Whisper 語言清單動態（/audio/transcribe/languages）;None=自動偵測
      { name: 'source_language', type: 'string', advanced: true },
      { name: 'vocal_separation', type: 'boolean', default: false },
      { name: 'translate', type: 'boolean', default: false },
      ...translateSubFields((p) => p.translate === true),
      { name: 'summarize', type: 'boolean', default: false },
      { name: 'summarize_model_family', type: 'string', default: 'gemma4', advanced: true, visibleWhen: (p) => p.summarize === true },
      { name: 'summarize_model_size', type: 'string', default: '4b', advanced: true, visibleWhen: (p) => p.summarize === true },
      { name: 'summarize_quantization', type: 'string', advanced: true, visibleWhen: (p) => p.summarize === true },
      { name: 'summarize_remote', type: 'boolean', default: false, advanced: true, visibleWhen: (p) => p.summarize === true },
      { name: 'summarize_provider', type: 'string', advanced: true, visibleWhen: (p) => p.summarize === true },
      { name: 'summarize_conn_id', type: 'number', advanced: true, visibleWhen: (p) => p.summarize === true },
      { name: 'summarize_remote_model', type: 'string', advanced: true, visibleWhen: (p) => p.summarize === true },
      // Whisper 進階（A1）
      { name: 'align', type: 'boolean', default: false, advanced: true },
      { name: 'word_timestamps', type: 'boolean', default: false, advanced: true },
      { name: 'condition_on_previous_text', type: 'boolean', default: true, advanced: true },
      { name: 'min_silence_duration_ms', type: 'number', min: 0, step: 50, default: 200, advanced: true },
      { name: 'vad_threshold', type: 'number', min: 0, max: 1, step: 0.05, default: 0.3, advanced: true },
    ],
  },

  'audio.volume': {
    toolKey: 'audio.volume',
    apiPath: '/audio/volume',
    labelKey: 'audio.volume.adjust_label',
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    paramSchema: [
      { name: 'volume_db', type: 'number', min: -30, max: 30, step: 1, default: 0 },
      { name: 'normalize', type: 'boolean', default: false },
    ],
  },

  'audio.cut': {
    toolKey: 'audio.cut',
    apiPath: '/audio/cut',
    labelKey: 'audio.cut.task_label',
    kind: 'tool',
    inputKinds: ['audio'],
    outputKind: AUDIO_OUT,
    // 後端合約是 HH:MM:SS 字串(AudioCutRequest),與 video.cut 的秒數 float
    // 不同 — string 欄位,default 照後端
    paramSchema: [
      { name: 'start_time', type: 'string', default: '00:00:00' },
      { name: 'end_time', type: 'string' },
    ],
  },

  // ── image ─────────────────────────────────────────────────────────
  'image.compress': {
    toolKey: 'image.compress',
    apiPath: '/image/compress',
    labelKey: 'image.compress.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: [
      { name: 'strength', type: 'number', min: 1, max: 100, step: 1, default: 60 },
      { name: 'gif_colors', type: 'number', min: 2, max: 256, step: 1, advanced: true },
      { name: 'gif_frame_drop', type: 'number', min: 0, step: 1, default: 0, advanced: true },
      { name: 'gif_optimize_transparency', type: 'boolean', default: true, advanced: true },
      { name: 'png_lossy', type: 'boolean', default: true, advanced: true },
      { name: 'jpeg_progressive', type: 'boolean', default: true, advanced: true },
      { name: 'jpeg_keep_metadata', type: 'boolean', default: false, advanced: true },
      { name: 'webp_lossless', type: 'boolean', default: false, advanced: true },
    ],
  },

  'image.convert': {
    toolKey: 'image.convert',
    apiPath: '/image/convert',
    labelKey: 'image.convert.task_label',
    kind: 'tool',
    inputKinds: ['image'],
    outputKind: IMAGE_OUT,
    paramSchema: [
      { name: 'output_format', type: 'enum', options: ['png', 'jpg', 'webp', 'gif', 'bmp'], default: 'png' },
      { name: 'quality', type: 'number', min: 1, max: 100, step: 1, default: 85, visibleWhen: (p) => ['jpg', 'webp'].includes(String(p.output_format)) },
      { name: 'width', type: 'number', min: 1, step: 1, advanced: true },
      { name: 'height', type: 'number', min: 1, step: 1, advanced: true },
      { name: 'scale', type: 'number', min: 0.1, max: 2, step: 0.1, advanced: true },
      { name: 'coalesce', type: 'boolean', default: false, advanced: true, visibleWhen: (p) => p.output_format === 'gif' },
    ],
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

  'document.translate': {
    toolKey: 'document.translate',
    apiPath: '/document/translate',
    labelKey: 'document.translate.task_label',
    kind: 'tool',
    inputKinds: ['document'],
    outputKind: DOCUMENT_OUT,
    // glossary（dict）v1 不建模——見檔頭註記
    paramSchema: [
      { name: 'source_language', type: 'string' },   // 必填、BCP 47,語言清單動態
      { name: 'target_language', type: 'string' },   // 必填、BCP 47
      { name: 'translate_style', type: 'enum', options: TRANSLATE_STYLES, default: 'colloquial' },
      { name: 'model_family', type: 'string', default: 'gemma4', advanced: true },
      { name: 'model_size', type: 'string', default: '4b', advanced: true },
      { name: 'quantization', type: 'string', advanced: true },
      { name: 'remote', type: 'boolean', default: false, advanced: true },
      { name: 'provider', type: 'string', advanced: true },
      { name: 'conn_id', type: 'number', advanced: true },
      { name: 'remote_model', type: 'string', advanced: true },
    ],
  },
}

export function getToolSpec(toolKey: string): ToolSpec | undefined {
  return TOOL_REGISTRY[toolKey]
}

export function listToolSpecs(): ToolSpec[] {
  return Object.values(TOOL_REGISTRY)
}

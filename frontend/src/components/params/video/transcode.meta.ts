/**
 * video.transcode 參數 META（統一參數元件 spec §4）。
 * schema 準繩＝後端 TranscodeRequest（backend/app/api/routes/video/transcode.py）全集。
 *
 * 工具頁語境的 output_format 選單是「視訊＋動圖＋音訊」超集（沿舊 VideoTranscodePanel 格式清單），
 * 音訊格式在工具頁由 buildSubmit 分流到 /video/extract-audio；pipeline 語境沒有這層分流,
 * 節點若選了音訊格式，params 會照樣送去 /video/transcode（後端該路由對純音訊輸出並非設計目標，
 * 但欄位型別/enum 驗證不會擋——這是 spec 決策：schema 單一超集 + UI 層過濾,詳見批 1 Task 1.1 brief）。
 */
import type { ToolParamMeta } from '../types'

/** 工具頁 output_format 超集裡屬於「純音訊」的值——buildSubmit 分流／欄位可見性判斷共用 */
export const AUDIO_FORMATS = new Set(['mp3', 'aac', 'wav', 'flac'])
/** 無聲動圖格式：video_codec/audio_codec/crf 皆不適用（後端 docstring 明載） */
const ANIM_FORMATS = new Set(['gif', 'apng'])

function isAudioFmt(p: Record<string, unknown>): boolean {
  return AUDIO_FORMATS.has(String(p.output_format ?? ''))
}
function isAnimFmt(p: Record<string, unknown>): boolean {
  return ANIM_FORMATS.has(String(p.output_format ?? ''))
}
function hasResolution(p: Record<string, unknown>): boolean {
  return String(p.resolution ?? '').trim() !== ''
}

export const META: ToolParamMeta = {
  toolKey: 'video.transcode',
  apiPath: '/video/transcode',
  labelKey: 'video.transcode.task_label',
  taskType: 'video.transcode',
  schema: [
    {
      name: 'output_format', type: 'enum',
      options: ['mp4', 'mkv', 'webm', 'avi', 'mov', 'gif', 'apng', 'mp3', 'aac', 'wav', 'flac'],
      default: 'mp4',
    },
    // 視訊/畫質欄位——純音訊、無聲動圖皆不適用
    { name: 'video_codec', type: 'enum', options: ['h264', 'h265', 'vp9', 'av1', 'copy'], default: 'h264',
      visibleWhen: (p) => !isAudioFmt(p) && !isAnimFmt(p) },
    { name: 'crf', type: 'number', min: 0, max: 51, step: 1, default: 23, advanced: true,
      visibleWhen: (p) => !isAudioFmt(p) && !isAnimFmt(p) },
    // 音訊編碼——無聲動圖不適用(anim 恆 -an);純音訊/一般視訊皆可能有音軌
    { name: 'audio_codec', type: 'enum', options: ['aac', 'mp3', 'opus', 'flac', 'copy'], default: 'aac', advanced: true,
      visibleWhen: (p) => !isAnimFmt(p) },
    { name: 'preset', type: 'enum', options: ['ultrafast', 'fast', 'medium', 'slow', 'veryslow'], default: 'medium', advanced: true },
    // resolution 為自由字串(元件把 custom 尺寸組成 "WxH" 再寫進來)——型別故意不設 enum,
    // 避免 normalizeParams 的 enum options 白名單擋掉自訂尺寸;格式檢查交給下方 validate()。
    { name: 'resolution', type: 'string', default: '', agentHint: 'empty = keep original, or "WIDTHxHEIGHT"' },
    { name: 'scale_algorithm', type: 'enum', options: ['bicubic', 'lanczos', 'spline', 'bilinear', 'neighbor'], default: 'bicubic', advanced: true,
      visibleWhen: (p) => !isAudioFmt(p) && hasResolution(p) },
    // fps：後端 docstring 定位為「動圖幀率」;一般視訊路徑舊 panel 未曾送出
    { name: 'fps', type: 'number', min: 0.1, max: 60, step: 1, advanced: true, agentHint: 'seconds^-1, anim only',
      visibleWhen: (p) => isAnimFmt(p) },
    { name: 'audio_bitrate', type: 'enum', options: ['128k', '192k', '256k', '320k'], advanced: true,
      visibleWhen: (p) => isAudioFmt(p) && !['wav', 'flac'].includes(String(p.output_format)) },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // resolution 寬鬆驗證：空字串（保持原始）或 "WxH" 皆合法;custom 尺寸已由元件組字串,
  // 這裡只擋手動/agent 塞入的畸形值。
  validate(params) {
    const r = String(params.resolution ?? '').trim()
    if (r === '' || /^\d+x\d+$/.test(r)) return null
    return 'video.transcode.resolution_error'
  },
  // 工具頁專屬：output_format 若為純音訊格式,改分流到 /video/extract-audio。
  // 後端 TranscodeRequest 真的收 audio_bitrate 欄位(ffmpeg.py 的 -b:a 組裝在
  // options.audio_codec!=copy 分支、與 resolution 無關)——故視訊/動圖路徑不刪這欄,
  // 照樣透傳(舊 panel 從未送過是 UI 侷限,非後端限制;此為本 task 的 spec 決策)。
  buildSubmit(params) {
    const fmt = String(params.output_format ?? '')
    if (AUDIO_FORMATS.has(fmt)) {
      const payload: Record<string, unknown> = { audio_format: fmt }
      if (params.audio_bitrate !== undefined && !['wav', 'flac'].includes(fmt)) {
        payload.audio_bitrate = params.audio_bitrate
      }
      return {
        apiPath: '/video/extract-audio',
        payload,
        taskType: 'video.extract_audio',
        labelKey: 'video.transcode.extract_audio',
      }
    }
    return {
      apiPath: this.apiPath,
      payload: { ...params },
      taskType: this.taskType,
      labelKey: this.labelKey,
    }
  },
  downloadFormatField: 'output_format',
  multiSelect: true,
}

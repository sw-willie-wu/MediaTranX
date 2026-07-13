/**
 * audio.transcode 參數 META（統一參數元件 spec §4；批 3 Task 3.1）。
 * schema 準繩＝後端 AudioTranscodeRequest（backend/app/api/routes/audio/transcode.py）全集，
 * 含 wma（_FORMAT_CODEC_MAP 準繩）——舊 AudioTranscodePanel 的 formats 常量沒有 wma 選項，
 * 這是 UI 侷限非後端限制，schema 仍列入全集；AudioTranscodeParams.vue 的下拉選單過濾掉 wma
 * （沿舊 panel，見批 3 batch3-recon.md §1(a)「wma 不入 UI 選單」設計定案）。
 * channels 是舊 panel 完全沒有的欄位（後端 Optional[int] ge1 le2）——佈局鐵則落 advanced 新增 UI。
 */
import type { ToolParamMeta } from '../types'

/** 後端 _FORMAT_CODEC_MAP 無損格式（不需要 bitrate）——沿舊 AudioTranscodePanel LOSSLESS_FORMATS 常量 */
export const LOSSLESS_FORMATS = new Set(['flac', 'alac', 'wav', 'aiff'])

export const META: ToolParamMeta = {
  toolKey: 'audio.transcode',
  apiPath: '/audio/transcode',
  labelKey: 'audio.transcode.task_label',
  taskType: 'audio.transcode',
  schema: [
    {
      name: 'output_format', type: 'enum',
      options: ['mp3', 'aac', 'm4a', 'ogg', 'opus', 'wma', 'flac', 'alac', 'wav', 'aiff'],
      default: 'mp3',
    },
    { name: 'audio_bitrate', type: 'enum', options: ['128k', '192k', '256k', '320k'], default: '192k', advanced: true,
      visibleWhen: (p) => !LOSSLESS_FORMATS.has(String(p.output_format ?? 'mp3')) },
    { name: 'sample_rate', type: 'number', min: 8000, max: 192000, step: 100, advanced: true,
      agentHint: 'empty/omitted = keep original sample rate' },
    { name: 'channels', type: 'number', min: 1, max: 2, step: 1, advanced: true,
      agentHint: 'empty/omitted = keep original channel count; 1=mono, 2=stereo' },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // 鏡射舊 AudioTranscodePanel.getParams()/execute() 語意（兩處原本各複製一份，統一元件收斂成
  // 單一 buildSubmit）：無損格式或 audio_bitrate 未設/空字串 → 剔除該欄（讓後端 default="192k"
  // 生效，"保持原始" 選項即此意）；sample_rate 空 → 明確送 null（非省略欄位，核對舊 panel :22）；
  // channels 為新欄位、舊 panel 無此語意——僅在使用者實際選了 1/2 時才送出，未選則省略
  // （後端 Optional[int]=None 省略/null 效果相同，這裡選擇省略——沒有舊行為要鏡射）。
  buildSubmit(params) {
    const fmt = String(params.output_format ?? 'mp3')
    const payload: Record<string, unknown> = { output_format: fmt }
    if (!LOSSLESS_FORMATS.has(fmt) && params.audio_bitrate) {
      payload.audio_bitrate = params.audio_bitrate
    }
    payload.sample_rate = typeof params.sample_rate === 'number' ? params.sample_rate : null
    if (typeof params.channels === 'number') {
      payload.channels = params.channels
    }
    return {
      apiPath: this.apiPath,
      payload,
      taskType: this.taskType,
      labelKey: this.labelKey,
    }
  },
  agentExecuteLabel: 'panel.audio_transcode.execute',
  downloadFormatField: 'output_format',
  multiSelect: true,
}

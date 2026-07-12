/**
 * video.cut 參數 META（統一參數元件 spec §4）。
 * schema 準繩＝後端 CutRequest（backend/app/api/routes/video/transcode.py）；
 * 秒數詞彙（number），HH:MM:SS 只是 UI 顯示層（CutParams/VideoView 橋接用下方 helper）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'video.cut',
  apiPath: '/video/cut',
  labelKey: 'video.cut.task_label',
  taskType: 'video.cut',
  schema: [
    { name: 'start_time', type: 'number', min: 0, step: 0.1, agentHint: 'seconds' },
    { name: 'end_time', type: 'number', min: 0.1, step: 0.1, agentHint: 'seconds' },
    { name: 'stream_copy', type: 'boolean', default: true, advanced: true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  validate(params) {
    const s = Number(params.start_time), e = Number(params.end_time)
    if (Number.isFinite(s) && Number.isFinite(e) && e <= s) return 'video.cut.time_error'
    return null
  },
  multiSelect: false,
  // 語意鏡射 VideoView 現行 watch(mediaInfo)：換檔把 end 無條件重填成影片總長、不動已存在的 start；
  // start 僅在未定義時補 0（鏡射舊工具頁「未動過就送 0」）。pipeline 不經此 hook。
  seedOnFileChange(info, current) {
    const d = info?.duration
    if (typeof d !== 'number' || d <= 0) return null
    return { end_time: d, ...(current.start_time === undefined ? { start_time: 0 } : {}) }
  },
}

/** 'HH:MM:SS' | 'MM:SS' | 秒字串 → 秒（沿 VideoCutPanel 既有邏輯） */
export function parseTimeToSeconds(time: string): number {
  const parts = time.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return Number(time) || 0
}

/** 秒 → 'HH:MM:SS'（undefined/非法 → '00:00:00'；小數截去） */
export function secondsToTime(s: number | undefined): string {
  const n = typeof s === 'number' && Number.isFinite(s) && s > 0 ? Math.floor(s) : 0
  const h = Math.floor(n / 3600), m = Math.floor((n % 3600) / 60), sec = n % 60
  return [h, m, sec].map(v => String(v).padStart(2, '0')).join(':')
}

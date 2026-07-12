/**
 * audio.cut 參數 META（統一參數元件 spec §4；批 3 Task 3.2）。
 * schema 準繩＝後端 AudioCutRequest（backend/app/api/routes/audio/cut.py）：
 * start_time/end_time 都是 **HH:MM:SS 字串**（vs video.cut 後端秒數 float——詞彙不同，
 * 勿混；此檔獨立於 video/cut.meta.ts，不共用其 parseTimeToSeconds/secondsToTime）。
 * end_time 後端無 default（必填）；schema 沿此不設 default，defaults() 因此只含 start_time。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'audio.cut',
  apiPath: '/audio/cut',
  labelKey: 'audio.cut.task_label',
  taskType: 'audio.cut',
  schema: [
    { name: 'start_time', type: 'string', default: '00:00:00', agentHint: 'HH:MM:SS' },
    { name: 'end_time', type: 'string', agentHint: 'HH:MM:SS' },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // end 非空且 parse 後 end>start 否則回 i18n key（沿舊 AudioCutPanel 沒有的前端驗證——
  // 舊版無驗證直接送後端，422 才會擋；本案把「後端必填無 default」的邊界提前到前端擋）。
  validate(params) {
    const endRaw = params.end_time
    if (typeof endRaw !== 'string' || endRaw.trim() === '') return 'audio.cut.time_error'
    const s = timeToSeconds(String(params.start_time ?? '00:00:00'))
    const e = timeToSeconds(endRaw)
    if (e <= s) return 'audio.cut.time_error'
    return null
  },
  multiSelect: false,
  // 語意鏡射舊 AudioCutPanel 的 watch(duration, immediate)：檔案切換／載入時，只要 duration
  // 可用就無條件重填 start=dur*0.2／end=dur*0.8（不像 video.cut 只補未定義欄位）；無 duration
  // 回 null（沿共用約束「pipeline 不 seed」——pipeline context 不傳 fileInfo，此 hook 不會被呼叫）。
  seedOnFileChange(info, _current) {
    const d = info?.duration
    if (typeof d !== 'number' || d <= 0) return null
    return { start_time: secondsToTime(d * 0.2), end_time: secondsToTime(d * 0.8) }
  },
  // 舊 AudioCutPanel 無 agentSchema/useAgentPanelHost——host 自動曝 start_time/end_time
  // 字串欄位是行為新增（沿 CropParams.vue 先例接受），agentRequiresConfirm/agentExecuteLabel
  // 皆不設、退回 host 預設（true／labelKey）。
}

/** 'HH:MM:SS' | 'MM:SS' | 純數字字串 → 秒（沿舊 AudioCutPanel.timeToSeconds 實作） */
export function timeToSeconds(str: string): number {
  const parts = str.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return parts[0] || 0
}

/** 秒 → 'HH:MM:SS'（undefined/非法/負數 → '00:00:00'；小數截去） */
export function secondsToTime(s: number | undefined): string {
  const n = typeof s === 'number' && Number.isFinite(s) && s > 0 ? Math.floor(s) : 0
  const h = Math.floor(n / 3600)
  const m = Math.floor((n % 3600) / 60)
  const sec = n % 60
  return [h, m, sec].map((v) => String(v).padStart(2, '0')).join(':')
}

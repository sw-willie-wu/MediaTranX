/**
 * video.extract_audio 參數 META（統一參數元件 spec §4）。
 * schema 準繩＝後端 ExtractAudioRequest（backend/app/api/routes/video/transcode.py）全集。
 * 純 pipeline 節點用（工具頁沒有獨立掛載點——音訊格式在 video.transcode 工具頁由
 * buildSubmit 分流到 /video/extract-audio，見 transcode.meta.ts）；無 buildSubmit,
 * params 直傳。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'video.extract_audio',
  apiPath: '/video/extract-audio',
  labelKey: 'video.transcode.extract_audio',
  taskType: 'video.extract_audio',
  schema: [
    { name: 'audio_format', type: 'enum', options: ['mp3', 'wav', 'flac', 'aac'], default: 'mp3' },
    { name: 'audio_bitrate', type: 'enum', options: ['128k', '192k', '256k', '320k'], advanced: true,
      visibleWhen: (p) => !['wav', 'flac'].includes(String(p.audio_format)) },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  multiSelect: true,
}

/**
 * audio.volume 參數 META（統一參數元件 spec §4；批 3 Task 3.1）。
 * schema 準繩＝後端 AudioVolumeRequest（backend/app/api/routes/audio/volume.py）全集：
 * volume_db ge-30 le30（UI 滑桿沿舊 panel 僅 ±20——agent/pipeline 仍可設到 ±30，見
 * VolumeParams.vue 檔頭註解）、normalize bool。
 *
 * agentRequiresConfirm=false 是本案（批 3）的第一個不同者：舊 AudioVolumePanel.agentSchema
 * .execute.requiresConfirm 為 false（音量調整非破壞性操作、免二次確認）——見 types.ts /
 * ToolParamHost.vue 新增的 meta.agentRequiresConfirm 選配欄位。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'audio.volume',
  apiPath: '/audio/volume',
  labelKey: 'audio.volume.adjust_label',
  taskType: 'audio.volume',
  schema: [
    { name: 'volume_db', type: 'number', min: -30, max: 30, step: 1, default: 0,
      // normalize 模式下 volume_db 恆送 0（見 buildSubmit）——agent 面板同步隱藏此欄，
      // 沿舊 agentSchema visibleWhen: mode==='adjust' 語意（mode 欄位已被 normalize 取代）。
      visibleWhen: (p) => p.normalize !== true },
    { name: 'normalize', type: 'boolean', default: false },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // 鏡射舊 AudioVolumePanel.getParams()/execute()（兩處原本各複製一份，收斂成單一
  // buildSubmit）：normalize=true 時 volume_db 一律送 0；labelKey 依 mode 分流（沿舊
  // normalize_label/adjust_label 兩個 task 列表顯示名稱，taskType 不分流、apiPath 不分流）。
  buildSubmit(params) {
    const normalize = params.normalize === true
    return {
      apiPath: this.apiPath,
      payload: {
        volume_db: normalize ? 0 : Number(params.volume_db ?? 0),
        normalize,
      },
      taskType: this.taskType,
      labelKey: normalize ? 'audio.volume.normalize_label' : 'audio.volume.adjust_label',
    }
  },
  agentRequiresConfirm: false,
  agentExecuteLabel: 'panel.volume.execute',
  multiSelect: true,
}

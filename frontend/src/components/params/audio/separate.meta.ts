/**
 * audio.separate 參數 META（統一參數元件 spec §4；批 3 Task 3.3）。
 * schema 準繩＝後端 AudioSeparateRequest（backend/app/api/routes/audio/separate.py）全集：
 * model_name enum（唯一 variant 'htdemucs_6s'，advanced——工具頁沿舊 panel 無 picker，見
 * SeparateParams.vue 檔頭）/ stems Optional[List[str]]（None=全部，list 型別，見下）/
 * output_format enum wav/flac/mp3（頂層）/ generate_midi boolean（頂層）。
 *
 * stems 不入 agent 欄位：ToolParamHost.agentFields 對 type==='list'/'dict' 一律濾除
 * （scalar set_field 無法表達陣列，見 ToolParamHost.vue 該段註解）——本檔不需另外標記，
 * type:'list' 已足夠讓 host 自動排除。舊 AudioSeparatePanel.agentSchema 曾把 stems 攤平成
 * 6 個 stem_* bool 欄位曝給 agent；新架構下 agent 欄位=後端詞彙、stems 是 UI 衍生非後端
 * 直接欄位，此為架構一致的刻意縮小（agent 面板欄位 model_name/output_format/generate_midi
 * 三欄，stems 缺席），記入報告。
 *
 * 例外殼裁決（Controller，task 3.3 brief）：plan 骨架原寫 separate 是例外殼（onTaskComplete
 * 留殼），但偵察顯示提交路徑是標準 submitTask、onTaskComplete 觸發源本來就在 AudioView
 * （historyStack watch）——改走標準 ToolParamHost 遷移，「彈窗問跳 MIDI」收訊邏輯上移
 * AudioView（見 AudioView.vue askJumpToMidi），本檔/SeparateParams.vue 僅管參數表單。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'audio.separate',
  apiPath: '/audio/separate',
  labelKey: 'audio.separate.task_label',
  taskType: 'audio.separate',
  schema: [
    { name: 'model_name', type: 'enum', options: ['htdemucs_6s'], default: 'htdemucs_6s', advanced: true },
    // 無 default——undefined=後端 None=全部音軌（見 SeparateParams.vue 衍生邏輯）
    { name: 'stems', type: 'list', itemType: 'string' },
    { name: 'output_format', type: 'enum', options: ['wav', 'flac', 'mp3'], default: 'wav' },
    { name: 'generate_midi', type: 'boolean', default: false },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // stems 為空陣列（使用者手動關掉全部 stem toggle）→ 擋下，鏡射舊 AudioSeparatePanel.isDisabled
  // 的 `selectedStems.length===0` 語意；undefined（=全部）合法放行。
  validate(params) {
    const stems = params.stems
    if (Array.isArray(stems) && stems.length === 0) return 'audio.separate.no_stems_selected'
    return null
  },
  // variant 型模型需求（同 interpolate/enhance 模式）：Demucs 單一家族/單一 variant，
  // categories 收斂在 modelStore category='separate' 範圍（見 backend/app/adapters/ai/registry.py
  // demucs entry category='separate'）。ToolParamHost.SLOT_GUARD_CATEGORY 已有 separate→'audio'
  // 對照（批 2 Task 2.4 預先補上），preflight 導覽到設定頁 audio 分類 tab。
  modelRequirement(params) {
    return { slot: 'separate', family: 'demucs', variant: String(params.model_name ?? 'htdemucs_6s'), categories: ['separate'] }
  },
  // 舊 AudioView.handleMultiExecute 的 'separate' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 AudioSeparatePanel.agentSchema.execute.label 是 'panel.separate.execute'，與
  // labelKey('audio.separate.task_label') 不同——沿 interpolate/volume 先例用 agentExecuteLabel
  // 承接。agentRequiresConfirm 不設（舊 panel requiresConfirm=true，與 host 預設相同）。
  agentExecuteLabel: 'panel.separate.execute',
}
